from enum import Enum
from fractions import Fraction
from math import floor, ceil
from typing import Optional, NamedTuple, Dict, Any, List, Tuple

from logzero import logger

from arbitrageur.items import Item, vendor_price, is_common_ascended_material
from arbitrageur.listings import ItemListings
from arbitrageur.prices import Price, effective_buy_price
from arbitrageur.recipes import Recipe, is_time_gated


class Source(Enum):
    Crafting = 0
    TradingPost = 1
    Vendor = 2


class CraftingCost(NamedTuple):
    cost: int
    source: Source
    time_gated: Optional[bool]
    needs_ascended: Optional[bool]


class ProfitableItem(NamedTuple):
    id: int
    crafting_cost: int
    crafting_steps: Fraction
    count: int
    profit: int
    time_gated: bool
    needs_ascended: bool


def profit_per_item(item: ProfitableItem) -> int:
    return floor(item.profit / item.count)


def profit_per_crafting_step(item: ProfitableItem) -> int:
    return floor(item.profit / item.crafting_steps)


def profit_on_cost(item: ProfitableItem) -> Fraction:
    return Fraction(item.profit, item.crafting_cost)


# integer division rounding up
# see: https://stackoverflow.com/questions/2745074/fast-ceiling-of-an-integer-division-in-c-c
def div_int_ceil(x: int, y: int) -> int:
    return (x + y - 1) // y


def inner_min(left: Optional[Any], right: Optional[Any]) -> Optional[Any]:
    if left is None:
        return right

    if right is None:
        return left

    return min(left, right)


# Calculate the lowest cost method to obtain the given item, with simulated purchases from
# the trading post.
def calculate_precise_min_crafting_cost(
        item_id: int,
        recipes_map: Dict[int, Recipe],
        items_map: Dict[int, Item],
        tp_listings_map: Dict[int, ItemListings],
        tp_purchases: List[Tuple[int, Fraction]],
        crafting_steps: Fraction) -> Tuple[Optional[CraftingCost], List[Tuple[int, Fraction]], Fraction]:
    assert item_id in items_map
    item = items_map.get(item_id)

    tp_purchases_ptr = len(tp_purchases)
    crafting_steps_before = crafting_steps

    crafting_cost = None
    time_gated = False
    needs_ascended = is_common_ascended_material(item)

    if item_id in recipes_map:
        recipe = recipes_map[item_id]

        time_gated = is_time_gated(recipe)

        if recipe.output_item_count is None:
            output_item_count = 1
        else:
            output_item_count = recipe.output_item_count

        cost = None
        logger.debug(f"""Calculating ingredients cost for {recipe.output_item_id}({items_map[recipe.output_item_id].name})""")
        for ingredient in recipe.ingredients:
            tp_purchases_ingredient_ptr = len(tp_purchases)
            crafting_steps_before_ingredient = crafting_steps

            ingredient_cost, tp_purchases, crafting_steps = calculate_precise_min_crafting_cost(
                ingredient.item_id,
                recipes_map,
                items_map,
                tp_listings_map,
                tp_purchases,
                crafting_steps)

            if ingredient_cost is None:
                # Rollback crafting
                return None, tp_purchases[:tp_purchases_ptr], crafting_steps_before

            if ingredient_cost.time_gated is not None:
                time_gated |= ingredient_cost.time_gated

            if ingredient_cost.needs_ascended is not None:
                needs_ascended |= ingredient_cost.needs_ascended

            if ingredient_cost.cost is None:
                # Rollback crafting
                return None, tp_purchases[:tp_purchases_ptr], crafting_steps_before
            else:
                # NB: The trading post prices won't be completely accurate, because the reductions
                # in liquidity for ingredients are deferred until the parent recipe is fully completed.
                # This is to allow trading post purchases to be 'rolled back' if crafting a parent
                # item turns out to be less profitable than buying it.
                if ingredient_cost.source == Source.TradingPost:
                    tp_purchases.append((ingredient.item_id, Fraction(ingredient.count, output_item_count)))
                elif ingredient_cost.source == Source.Crafting:
                    # repeat purchases of the ingredient's children
                    new_purchases = [(item, cost * ingredient.count / output_item_count) for (item, cost) in
                                     tp_purchases[tp_purchases_ingredient_ptr:]]
                    tp_purchases = tp_purchases[:tp_purchases_ingredient_ptr] + new_purchases

                    crafting_steps = crafting_steps_before_ingredient + (
                            crafting_steps - crafting_steps_before_ingredient) * ingredient.count / output_item_count

                if cost is None:
                    cost = ingredient_cost.cost * ingredient.count
                else:
                    cost += ingredient_cost.cost * ingredient.count

        if cost is None:
            crafting_cost = None
        else:
            crafting_cost = div_int_ceil(cost, output_item_count)

    if item_id in tp_listings_map:
        tp_cost = tp_listings_map.get(item_id).lowest_sell_offer(1)
    else:
        tp_cost = None

    vendor_cost = vendor_price(item)

    logger.debug(f"""Crafting/TP/Vendor costs for {item_id}({items_map[item_id].name}) are {crafting_cost}/{tp_cost}/{vendor_cost}""")
    lowest_cost = select_lowest_cost(crafting_cost, tp_cost, vendor_cost, time_gated, needs_ascended)
    if lowest_cost.source != Source.Crafting:
        # Rollback crafting
        tp_purchases = tp_purchases[:tp_purchases_ptr]
        crafting_steps = crafting_steps_before
    else:
        # increment crafting steps here, so that the final item
        # itself is also included in the crafting step count.
        crafting_steps += Fraction(1, output_item_count)

    return lowest_cost, tp_purchases, crafting_steps


def calculate_crafting_profit(
        listings: ItemListings,
        recipes_map: Dict[int, Recipe],
        items_map: Dict[int, Item],
        tp_listings_map: Dict[int, ItemListings],
        purchased_ingredients: Optional[Dict[int, Fraction]]) -> Tuple[ProfitableItem, Optional[Dict[int, Fraction]]]:
    listing_profit = 0
    total_crafting_cost = 0
    crafting_count = 0
    total_crafting_steps = Fraction(0)

    while True:
        logger.debug(f"""Calculating profits for {listings.id}({items_map[listings.id].name}) #{crafting_count}""")
        crafting_steps = Fraction(0)

        tp_purchases = []
        crafting_cost, tp_purchases, crafting_steps = calculate_precise_min_crafting_cost(listings.id,
                                                                                          recipes_map,
                                                                                          items_map,
                                                                                          tp_listings_map,
                                                                                          tp_purchases,
                                                                                          crafting_steps)

        if crafting_cost is None:
            break

        buy_price = listings.sell()

        if buy_price is None:
            break

        profit = effective_buy_price(buy_price) - crafting_cost.cost

        logger.debug(f"""Buy price {listings.id}({items_map[listings.id].name}) #{crafting_count} is {buy_price} before tax, {effective_buy_price(buy_price)} after tax""")
        logger.debug(f"""Profit {listings.id}({items_map[listings.id].name}) #{crafting_count} is {buy_price} - {crafting_cost.cost} = {profit}""")

        if profit > 0:
            listing_profit += profit
            total_crafting_cost += crafting_cost.cost
            crafting_count += 1
        else:
            break

        for (item_id, count) in tp_purchases:
            assert item_id in tp_listings_map, f"""Missing detailed prices for {item_id}"""
            bought = tp_listings_map[item_id].buy(ceil(count))
            assert bought is not None

        if purchased_ingredients is not None:
            for (item_id, count) in tp_purchases:
                if item_id in purchased_ingredients:
                    purchased_ingredients[item_id] += count
                else:
                    purchased_ingredients[item_id] = count

        total_crafting_steps += crafting_steps

    return ProfitableItem(
        id=listings.id,
        crafting_cost=total_crafting_cost,
        crafting_steps=total_crafting_steps,
        profit=listing_profit,
        count=crafting_count,
        time_gated=crafting_cost.time_gated,
        needs_ascended=crafting_cost.needs_ascended), purchased_ingredients


def select_lowest_cost(crafting_cost: Optional[int],
                       tp_cost: Optional[int],
                       vendor_cost: Optional[int],
                       time_gated: Optional[bool],
                       needs_ascended: Optional[bool]) -> CraftingCost:
    cost = inner_min(inner_min(tp_cost, crafting_cost), vendor_cost)
    # give trading post precedence over crafting if costs are equal
    if tp_cost is not None:
        source = Source.TradingPost
    elif crafting_cost is not None:
        source = Source.Crafting
    else:
        source = Source.Vendor
    return CraftingCost(cost, source, time_gated, needs_ascended)


# Calculate the lowest cost method to obtain the given item, using only the current high/low tp prices.
# This may involve a combination of crafting, trading and buying from vendors.
def calculate_estimated_min_crafting_cost(
        item_id: int,
        recipes_map: Dict[int, Recipe],
        items_map: Dict[int, Item],
        tp_prices_map: Dict[int, Price]) -> Optional[CraftingCost]:
    assert item_id in items_map
    item = items_map.get(item_id)

    crafting_cost = None
    time_gated = False
    needs_ascended = is_common_ascended_material(item)

    recipe = recipes_map.get(item_id)
    if recipe is not None:
        time_gated = is_time_gated(recipe)

        cost = 0
        for ingredient in recipe.ingredients:
            ingredient_cost = calculate_estimated_min_crafting_cost(
                ingredient.item_id,
                recipes_map,
                items_map,
                tp_prices_map)

            if ingredient_cost is None:
                return None

            if ingredient_cost.time_gated is not None:
                time_gated |= ingredient_cost.time_gated

            if ingredient_cost.needs_ascended is not None:
                needs_ascended |= ingredient_cost.needs_ascended

            if ingredient_cost.cost is None:
                return None
            else:
                cost += ingredient_cost.cost * ingredient.count

        if recipe.output_item_count is None:
            output_item_count = 1
        else:
            output_item_count = recipe.output_item_count

        crafting_cost = div_int_ceil(cost, output_item_count)

    price = tp_prices_map.get(item_id)
    if price is None:
        tp_cost = None
    elif price.sells.quantity == 0:
        tp_cost = None
    else:
        tp_cost = price.sells.unit_price

    vendor_cost = vendor_price(item)

    return select_lowest_cost(crafting_cost, tp_cost, vendor_cost, time_gated, needs_ascended)
