import asyncio
from math import ceil

import logzero
from pathlib import Path
from typing import Dict, List, Tuple

from arbitrageur.crafting import calculate_estimated_min_crafting_cost, calculate_crafting_profit, \
    profit_per_crafting_step
from arbitrageur.export import export_csv, export_excel
from arbitrageur.items import Item, is_restricted, retrieve_items
from arbitrageur.listings import retrieve_detailed_tp_listings
from arbitrageur.prices import Price, effective_buy_price, retrieve_tp_prices
from arbitrageur.recipes import Recipe, collect_ingredient_ids, retrieve_recipes

from logzero import logger

FILTER_DISCIPLINES = [
    "Armorsmith",
    "Artificer",
    "Chef",
    "Huntsman",
    "Jeweler",
    "Leatherworker",
    "Scribe",
    "Tailor",
    "Weaponsmith",
]  # only show items craftable by these disciplines

ITEM_STACK_SIZE = 250  # GW2 uses a "stack size" of 250


def calculate_profitable_items(items_map: Dict[int, Item],
                               recipes_map: Dict[int, Recipe],
                               tp_prices_map: Dict[int, Price]) -> Tuple[List[int], List[int]]:
    logger.info("Computing profitable item list")
    profitable_item_ids = []
    ingredient_ids = []
    for item_id, recipe in recipes_map.items():
        item = items_map.get(item_id)
        if item is not None:
            # We cannot sell restricted items
            if is_restricted(item):
                continue

        # Check if any of the disciplines we want to use can craft the item
        has_discipline = any(discipline in recipe.disciplines for discipline in FILTER_DISCIPLINES)
        if not has_discipline:
            continue

        # some items are craftable and have no listed restrictions but are still not listable on tp
        # e.g. 39417, 79557
        # conversely, some items have a NoSell flag but are listable on the trading post
        # e.g. 66917
        tp_prices = tp_prices_map.get(item_id)
        if tp_prices is None:
            continue

        if tp_prices.sells.quantity == 0:
            continue

        crafting_cost = calculate_estimated_min_crafting_cost(item_id, recipes_map, items_map, tp_prices_map)
        if crafting_cost is not None:
            if effective_buy_price(tp_prices.buys.unit_price) > crafting_cost.cost:
                profitable_item_ids.append(item_id)
                ingredient_ids += collect_ingredient_ids(item_id, recipes_map)
    return ingredient_ids, profitable_item_ids


async def retrieve_profitable_items(items_map, recipes_map):
    tp_prices_map = await retrieve_tp_prices()
    ingredient_ids, profitable_item_ids = calculate_profitable_items(items_map,
                                                                     recipes_map,
                                                                     tp_prices_map)
    request_listing_item_ids = set(profitable_item_ids)
    request_listing_item_ids.update(ingredient_ids)
    tp_listings_map = await retrieve_detailed_tp_listings(list(request_listing_item_ids))
    logger.info("Computing precise crafting profits")
    profitable_items = []
    for item_id in profitable_item_ids:
        assert item_id in tp_listings_map
        item_listings = tp_listings_map[item_id]
        profitable_item = calculate_crafting_profit(item_listings,
                                                    recipes_map,
                                                    items_map,
                                                    tp_listings_map)
        profitable_items.append(profitable_item)
    profitable_items.sort(key=lambda pi: pi.profit)
    return profitable_items


async def main():
    recipes_path = Path("recipes.json")
    items_path = Path("items.json")

    recipes_map = await retrieve_recipes(recipes_path)
    items_map = await retrieve_items(items_path)

    # Change this to any item ID to generate a precise shopping list
    item_id = 11167

    if not item_id:
        profitable_items = await retrieve_profitable_items(items_map, recipes_map)
        export_csv(profitable_items, items_map, recipes_map)
        export_excel(profitable_items, items_map, recipes_map)
    else:
        assert item_id in items_map
        item = items_map[item_id]

        ingredient_ids = collect_ingredient_ids(item_id, recipes_map)

        request_listing_item_ids = {item_id}
        request_listing_item_ids.update(ingredient_ids)
        tp_listings_map = await retrieve_detailed_tp_listings(list(request_listing_item_ids))

        assert item_id in tp_listings_map
        item_listings = tp_listings_map[item_id]
        profitable_item = calculate_crafting_profit(item_listings,
                                                    recipes_map,
                                                    items_map,
                                                    tp_listings_map)

        if profitable_item.profit == 0:
            logger.warn(f"""Item {item_id}({items_map[item_id].name}) is not profitable to craft""")
            return

        logger.info("============")
        logger.info(
            f"""Shopping list for {profitable_item.count} x {item.name} = {profitable_item.profit} profit ({profit_per_crafting_step(profitable_item)} / step)""")
        logger.info("============")

        for (ingredient_id, ingredient_count_ratio) in profitable_item.purchased_ingredients.items():
            ingredient_count = ceil(ingredient_count_ratio)
            if ingredient_count < ITEM_STACK_SIZE:
                ingredient_count_msg = str(ingredient_count)
            else:
                stack_count = ingredient_count // ITEM_STACK_SIZE
                remainder = ingredient_count % ITEM_STACK_SIZE
                if remainder != 0:
                    remainder_msg = f""" + {remainder}"""
                else:
                    remainder_msg = ""

                ingredient_count_msg = f"""{ingredient_count} ({stack_count} x {ITEM_STACK_SIZE}{remainder_msg})"""

            logger.info(f"""{ingredient_count_msg} {items_map[ingredient_id].name} ({ingredient_id})""")


if __name__ == "__main__":
    logzero.loglevel(logzero.INFO)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
