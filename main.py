import asyncio
from pathlib import Path
from typing import Dict, List

from arbitrageur.crafting import CraftingOptions, calculate_estimated_min_crafting_cost
from arbitrageur.items import Item, ItemUpgrade, is_restricted
from arbitrageur.prices import Price, PriceInfo, effective_buy_price
from arbitrageur.recipes import Recipe, RecipeIngredient
from arbitrageur.request import request_cached_pages, request_all_pages, fetch_item_listings

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


def collect_ingredient_ids(item_id: int, recipes_map: Dict[int, Recipe]):
    ids = []
    recipe = recipes_map.get(item_id)
    if recipe:
        for ingredient in recipe.ingredients:
            ids.append(ingredient.item_id)
            ids += collect_ingredient_ids(ingredient.item_id, recipes_map)

    return ids


async def main():
    recipes_path = Path("recipes.json")
    items_path = Path("items.json")

    print("Loading recipes")
    recipes = await request_cached_pages(recipes_path, "recipes")
    print(f"""Loaded {len(recipes)} recipes""")

    print("Parsing recipes data")
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

    print("Loading items")
    items = await request_cached_pages(items_path, "items")
    print(f"""Loaded {len(items)} items""")

    print("Parsing items data")
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

    crafting_options = CraftingOptions(
        include_time_gated=True,
        include_ascended=True,
        count=None)

    print("Loading trading post prices")
    tp_prices = await request_all_pages("commerce/prices")
    print(f"""Loaded {len(tp_prices)} trading post prices""")

    print("Parsing trading post prices data")
    tp_prices_map = {price["id"]: Price(id=price["id"],
                                        buys=PriceInfo(unit_price=price["buys"]["unit_price"],
                                                       quantity=price["buys"]["quantity"]),
                                        sells=PriceInfo(unit_price=price["sells"]["unit_price"],
                                                        quantity=price["sells"]["quantity"])) for price in tp_prices}

    print("Computing profitable item list")
    profitable_item_ids = []
    ingredient_ids = []

    for item_id, recipe in recipes_map.items():
        item = items_map.get(item_id)
        if item is not None:
            # We cannot sell restricted items
            if is_restricted(item):
                continue

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

    print("Loading detailed trading post listings")
    request_listing_item_ids = set(profitable_item_ids)
    request_listing_item_ids.update(ingredient_ids)
    tp_listings = await fetch_item_listings(list(request_listing_item_ids))
    print(f"""Loaded {len(tp_listings)} detailed trading post listings""")

    print("TODO : Compute precise crafting profits")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
