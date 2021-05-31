from math import ceil
from pathlib import Path
from typing import List, NamedTuple, Dict

from logzero import logger

from arbitrageur.crafting import profit_per_crafting_step
from arbitrageur.request import request_cached_pages

ITEM_STACK_SIZE = 250  # GW2 uses a "stack size" of 250


class RecipeIngredient(NamedTuple):
    item_id: int
    count: int


class Recipe(NamedTuple):
    id: int
    type_name: str
    output_item_id: int
    output_item_count: int
    time_to_craft_ms: int
    disciplines: List[str]
    min_rating: int
    flags: List[str]
    ingredients: List[RecipeIngredient]
    chat_link: str


# see https://wiki.guildwars2.com/wiki/Category:Time_gated_recipes
# for a list of time gated recipes
# I've left Charged Quartz Crystals off the list, since they can
# drop from containers.
def is_time_gated(recipe: Recipe) -> bool:
    return any([recipe.output_item_id == 46740,  # Spool of Silk Weaving Thread
                recipe.output_item_id == 46742,  # Lump of Mithrillium
                recipe.output_item_id == 46744,  # Glob of Elder Spirit Residue
                recipe.output_item_id == 46745,  # Spool of Thick Elonian Cord
                recipe.output_item_id == 66913,  # Clay Pot
                recipe.output_item_id == 66917,  # Plate of Meaty Plant Food
                recipe.output_item_id == 66923,  # Plate of Piquant Plan Food
                recipe.output_item_id == 66993,  # Grow Lamp
                recipe.output_item_id == 67015,  # Heat Stone
                recipe.output_item_id == 67377,  # Vial of Maize Balm
                recipe.output_item_id == 79726,  # Dragon Hatchling Doll Eye
                recipe.output_item_id == 79763,  # Gossamer Stuffing
                recipe.output_item_id == 79790,  # Dragon Hatchling Doll Hide
                recipe.output_item_id == 79795,  # Dragon Hatchling Doll Adornments
                recipe.output_item_id == 79817])  # Dragon Hatchling Doll Frame


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


def collect_ingredient_ids(item_id: int, recipes_map: Dict[int, Recipe]) -> List[int]:
    ids = []
    recipe = recipes_map.get(item_id)
    if recipe:
        for ingredient in recipe.ingredients:
            ids.append(ingredient.item_id)
            ids += collect_ingredient_ids(ingredient.item_id, recipes_map)

    return ids


def format_json_recipe(profitable_item, items_map):
    logger.debug(
        f"""Shopping list for {profitable_item.count} x {items_map[profitable_item.id].name} = {profitable_item.profit} profit ({profit_per_crafting_step(profitable_item)} / step) :""")

    recipe = {}
    for ingredient_id, purchased_ingredient in profitable_item.purchased_ingredients.items():
        ingredient_count = ceil(purchased_ingredient.count)
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

        ingredient_name = items_map[ingredient_id].name
        logger.debug(
            f"""{ingredient_count_msg} {ingredient_name} ({ingredient_id}) for {purchased_ingredient.cost}""")

        recipe[ingredient_name] = {"count": ingredient_count_msg,
                                   "listings": purchased_ingredient.listings}
    return recipe
