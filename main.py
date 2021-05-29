import asyncio
from pathlib import Path
from typing import Dict, List, Tuple

from arbitrageur.crafting import CraftingOptions, calculate_estimated_min_crafting_cost, calculate_crafting_profit
from arbitrageur.items import Item, ItemUpgrade, is_restricted
from arbitrageur.listings import ItemListings, Listing
from arbitrageur.prices import Price, PriceInfo, effective_buy_price
from arbitrageur.recipes import Recipe, RecipeIngredient
from arbitrageur.request import request_cached_pages, request_all_pages, fetch_item_listings

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


async def retrieve_recipes(recipes_path: Path) -> Dict[int, Recipe]:
    logger.info("Loading recipes")
    recipes = await request_cached_pages(recipes_path, "recipes")
    logger.info(f"""Loaded {len(recipes)} recipes""")
    logger.info("Parsing recipes data")
    recipes_map = {recipe["output_item_id"]: Recipe(id=recipe["id"],
                                                    type_name=recipe["type"],
                                                    output_item_id=recipe["output_item_id"],
                                                    output_item_count=recipe["output_item_count"],
                                                    time_to_craft_ms=recipe["time_to_craft_ms"],
                                                    disciplines=recipe["disciplines"],
                                                    min_rating=recipe["min_rating"],
                                                    flags=recipe["flags"],
                                                    ingredients=[RecipeIngredient(item_id=i["item_id"],
                                                                                  count=i["count"]) for i in
                                                                 recipe["ingredients"]],
                                                    chat_link=recipe["chat_link"]) for recipe in recipes}
    return recipes_map


async def retrieve_items(items_path: Path) -> Dict[int, Item]:
    logger.info("Loading items")
    items = await request_cached_pages(items_path, "items")
    logger.info(f"""Loaded {len(items)} items""")
    logger.info("Parsing items data")
    items_map = {item["id"]: Item(id=item["id"],
                                  chat_link=item["chat_link"],
                                  name=item["name"],
                                  icon=item.get("icon"),
                                  description=item.get("description"),
                                  type_name=item["type"],
                                  rarity=item["rarity"],
                                  level=item["level"],
                                  vendor_value=item["vendor_value"],
                                  default_skin=item.get("default_skin"),
                                  flags=item["flags"],
                                  game_types=item["game_types"],
                                  restrictions=item["restrictions"],
                                  upgrades_into=None if "upgrades_into" not in item else [
                                      ItemUpgrade(item_id=i["item_id"], upgrade=i["upgrade"]) for i in
                                      item["upgrades_into"]],
                                  upgrades_from=None if "upgrades_from" not in item else [
                                      ItemUpgrade(item_id=i["item_id"], upgrade=i["upgrade"]) for i in
                                      item["upgrades_from"]]) for item in items}
    return items_map


async def retrieve_tp_prices() -> Dict[int, Price]:
    logger.info("Loading trading post prices")
    tp_prices = await request_all_pages("commerce/prices")
    logger.info(f"""Loaded {len(tp_prices)} trading post prices""")
    logger.info("Parsing trading post prices data")
    tp_prices_map = {price["id"]: Price(id=price["id"],
                                        buys=PriceInfo(unit_price=price["buys"]["unit_price"],
                                                       quantity=price["buys"]["quantity"]),
                                        sells=PriceInfo(unit_price=price["sells"]["unit_price"],
                                                        quantity=price["sells"]["quantity"])) for price in tp_prices}
    return tp_prices_map


def collect_ingredient_ids(item_id: int, recipes_map: Dict[int, Recipe]) -> List[int]:
    ids = []
    recipe = recipes_map.get(item_id)
    if recipe:
        for ingredient in recipe.ingredients:
            ids.append(ingredient.item_id)
            ids += collect_ingredient_ids(ingredient.item_id, recipes_map)

    return ids


def calculate_profitable_items(crafting_options: CraftingOptions,
                               items_map: Dict[int, Item],
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

        crafting_cost = calculate_estimated_min_crafting_cost(item_id, recipes_map, items_map, tp_prices_map,
                                                              crafting_options)
        if crafting_cost is not None:
            if effective_buy_price(tp_prices.buys.unit_price) > crafting_cost.cost:
                profitable_item_ids.append(item_id)
                ingredient_ids += collect_ingredient_ids(item_id, recipes_map)
    return ingredient_ids, profitable_item_ids


async def retrieve_detailed_tp_listings(item_ids: List[int]) -> Dict[int, ItemListings]:
    logger.info("Loading detailed trading post listings")
    tp_listings = await fetch_item_listings(item_ids)
    logger.info(f"""Loaded {len(tp_listings)} detailed trading post listings""")
    logger.info("Parsing detailed trading post listings data")
    tp_listings_map = {listings["id"]: ItemListings(id=listings["id"],
                                                    buys=[Listing(listings=listing["listings"],
                                                                  unit_price=listing["unit_price"],
                                                                  quantity=listing["quantity"]) for listing in
                                                          listings["buys"]],
                                                    sells=[Listing(listings=listing["listings"],
                                                                   unit_price=listing["unit_price"],
                                                                   quantity=listing["quantity"]) for listing in
                                                           listings["sells"]]) for listings in tp_listings}
    return tp_listings_map


async def main():
    recipes_path = Path("recipes.json")
    items_path = Path("items.json")

    recipes_map = await retrieve_recipes(recipes_path)
    items_map = await retrieve_items(items_path)

    crafting_options = CraftingOptions(
        include_time_gated=True,
        include_ascended=True,
        count=None)

    tp_prices_map = await retrieve_tp_prices()

    ingredient_ids, profitable_item_ids = calculate_profitable_items(crafting_options,
                                                                     items_map,
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
        profitable_item, _ = calculate_crafting_profit(item_listings,
                                                       recipes_map,
                                                       items_map,
                                                       tp_listings_map,
                                                       None,
                                                       crafting_options)
        profitable_items.append(profitable_item)

    logger.info("TODO : ??? PROFIT")
    profitable_items.sort(key=lambda pi: pi.profit)
    return profitable_items


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    profitable_items = loop.run_until_complete(main())
