from typing import List, NamedTuple


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
    return any(recipe.output_item_id == 46740,  # Spool of Silk Weaving Thread
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
               recipe.output_item_id == 79817)  # Dragon Hatchling Doll Frame
