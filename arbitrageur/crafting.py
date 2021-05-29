from enum import Enum
from fractions import Fraction
from math import floor, ceil
from typing import Optional, NamedTuple, Dict, Any, List, Tuple

from arbitrageur.items import Item, vendor_price, is_common_ascended_material
from arbitrageur.listings import ItemListings
from arbitrageur.prices import Price
from arbitrageur.recipes import Recipe, is_time_gated


class Source(Enum):
    Crafting = 0
    TradingPost = 1
    Vendor = 2


class CraftingOptions(NamedTuple):
    include_time_gated: bool
    include_ascended: bool
    count: Optional[int]


class CraftingCost(NamedTuple):
    cost: int
    source: Source


class ProfitableItem(NamedTuple):
    id: int
    crafting_cost: int
    crafting_steps: Fraction
    count: int
    profit: int


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


def calculate_precise_min_crafting_cost_internal(
        recipe: Recipe,
        output_item_count: int,
        recipes_map: Dict[int, Recipe],
        items_map: Dict[int, Item],
        tp_listings_map: Dict[int, ItemListings],
        tp_purchases: List[Tuple[int, Fraction]],
        crafting_steps: Fraction,
        opt: CraftingOptions) -> Tuple[Optional[int], List[Tuple[int, Fraction]], Fraction]:
    if not opt.include_time_gated and is_time_gated(recipe):
        return None, tp_purchases, crafting_steps

    cost = 0
    for ingredient in recipe.ingredients:
        tp_purchases_ingredient_ptr = len(tp_purchases)
        crafting_steps_before_ingredient = crafting_steps

        ingredient_cost, tp_purchases, crafting_steps = calculate_precise_min_crafting_cost(
            ingredient.item_id,
            recipes_map,
            items_map,
            tp_listings_map,
            tp_purchases,
            crafting_steps,
            opt)

        if ingredient_cost is None:
            return None, tp_purchases, crafting_steps

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

        cost += ingredient_cost * ingredient.count

    return div_int_ceil(cost, output_item_count), tp_purchases, crafting_steps


# Calculate the lowest cost method to obtain the given item, with simulated purchases from
# the trading post.
def calculate_precise_min_crafting_cost(
        item_id: int,
        recipes_map: Dict[int, Recipe],
        items_map: Dict[int, Item],
        tp_listings_map: Dict[int, ItemListings],
        tp_purchases: List[Tuple[int, Fraction]],
        crafting_steps: Fraction,
        opt: CraftingOptions) -> Tuple[CraftingCost, List[Tuple[int, Fraction]], Fraction]:
    assert item_id in items_map
    item = items_map.get(item_id)

    assert item_id in recipes_map
    recipe = recipes_map.get(item_id)

    if recipe.output_item_count is None:
        output_item_count = 1
    else:
        output_item_count = recipe.output_item_count

    tp_purchases_ptr = len(tp_purchases)
    crafting_steps_before = crafting_steps

    crafting_cost, tp_purchases, crafting_steps = calculate_precise_min_crafting_cost_internal(recipe,
                                                                                               output_item_count,
                                                                                               recipes_map, items_map,
                                                                                               tp_listings_map,
                                                                                               tp_purchases,
                                                                                               crafting_steps, opt)

    assert item_id in tp_listings_map
    tp_cost = tp_listings_map.get(item_id).lowest_sell_offer(1)

    if opt.include_ascended and is_common_ascended_material(item):
        vendor_cost = 0
    else:
        vendor_cost = vendor_price(item)

    lowest_cost = select_lowest_cost(crafting_cost, tp_cost, vendor_cost)
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
        purchased_ingredients: Optional[Dict[int, Fraction]],
        opt: CraftingOptions) -> Tuple[ProfitableItem, Optional[Dict[int, Fraction]]]:
    listing_profit = 0
    total_crafting_cost = 0
    crafting_count = 0
    total_crafting_steps = Fraction(0)

    while True:
        if opt.count is not None:
            if crafting_count >= opt.count:
                break

        tp_purchases = []
        crafting_steps = Fraction(0)

        crafting_cost, tp_purchases, crafting_steps = calculate_precise_min_crafting_cost(listings.id,
                                                                                          recipes_map,
                                                                                          items_map,
                                                                                          tp_listings_map,
                                                                                          tp_purchases,
                                                                                          crafting_steps,
                                                                                          opt)

        if crafting_cost is None:
            break

        buy_price = listings.sell()

        if buy_price is None:
            break

        profit = buy_price - crafting_cost.cost
        if profit > 0:
            listing_profit += profit
            total_crafting_cost += crafting_cost.cost
            crafting_count += 1
        else:
            break

        for (item_id, count) in tp_purchases:
            assert item_id in tp_listings_map  # Missing detailed prices for item id
            tp_listings_map.get(item_id).buy(ceil(count))

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
        count=crafting_count), purchased_ingredients


def select_lowest_cost(crafting_cost: Optional[int],
                       tp_cost: Optional[int],
                       vendor_cost: Optional[int]) -> CraftingCost:
    cost = inner_min(inner_min(tp_cost, crafting_cost), vendor_cost)
    # give trading post precedence over crafting if costs are equal
    if tp_cost is not None:
        source = Source.TradingPost
    elif crafting_cost is not None:
        source = Source.Crafting
    else:
        source = Source.Vendor
    return CraftingCost(cost, source)

# Calculate the lowest cost method to obtain the given item, using only the current high/low tp prices.
# This may involve a combination of crafting, trading and buying from vendors.
def calculate_estimated_min_crafting_cost(
        item_id: int,
        recipes_map: Dict[int, Recipe],
        items_map: Dict[int, Item],
        tp_prices_map: Dict[int, Price],
        opt: CraftingOptions) -> Optional[CraftingCost]:
    assert item_id in items_map
    item = items_map.get(item_id)

    recipe = recipes_map.get(item_id)
    if recipe is None:
        crafting_cost = None
    elif not opt.include_time_gated and is_time_gated(recipe):
        crafting_cost = None
    else:
        cost = 0
        for ingredient in recipe.ingredients:
            ingredient_cost = calculate_estimated_min_crafting_cost(
                ingredient.item_id,
                recipes_map,
                items_map,
                tp_prices_map,
                opt)

            if ingredient_cost is None:
                return None
            elif ingredient_cost.cost is None:
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

    if opt.include_ascended and is_common_ascended_material(item):
        vendor_cost = 0
    else:
        vendor_cost = vendor_price(item)

    return select_lowest_cost(crafting_cost, tp_cost, vendor_cost)
