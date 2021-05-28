import asyncio
from pathlib import Path

from arbitrageur.crafting import CraftingOptions
from arbitrageur.request import request_cached_pages

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


async def main():
    recipes_path = Path("recipes.json")
    items_path = Path("items.json")

    print("Loading recipes")
    recipes = await request_cached_pages(recipes_path, "recipes")
    print(f"""Loaded {len(recipes)} recipes""")

    print("Loading items")
    items = await request_cached_pages(items_path, "items")
    print(f"""Loaded {len(items)} items""")

    print("Parsing JSON data")
    recipes_map = {recipe.output_item_id: recipe for recipe in recipes}
    items_map = {item.id: item for item in items}

    crafting_options = CraftingOptions(
        include_time_gated=True,
        include_ascended=True,
        count=None)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
