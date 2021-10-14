import asyncio
import json

import logzero
from pathlib import Path
from typing import Dict, List, Tuple

from arbitrageur.crafting import calculate_estimated_min_crafting_cost, calculate_crafting_profit, \
    profit_per_crafting_step
from arbitrageur.export import export_csv, export_excel, format_json_recipe
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
    profitable_items.sort(key=lambda pi: pi.profit, reverse=True)
    return profitable_items


async def retrieve_recipe(item_id, items_map, recipes_map):
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
        return None

    logger.info(
        f"""Shopping list for {profitable_item.count} x {item.name} = {profitable_item.profit} profit ({profit_per_crafting_step(profitable_item)} / step) :""")
    return format_json_recipe(profitable_item, items_map)


async def main():
    recipes_path = Path("recipes.json")
    items_path = Path("items.json")

    recipes_map = await retrieve_recipes(recipes_path)
    items_map = await retrieve_items(items_path)

    # Change this to any item ID to generate a precise shopping list
    item_id = None

    if not item_id:
        profitable_items = await retrieve_profitable_items(items_map, recipes_map)
        export_csv(profitable_items, items_map, recipes_map)
        export_excel(profitable_items, items_map, recipes_map, time_gated=False, needs_ascended=False)
    else:
        recipe = await retrieve_recipe(item_id, items_map, recipes_map)
        logger.info(json.dumps(recipe, indent=2))


if __name__ == "__main__":
    logzero.loglevel(logzero.INFO)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
