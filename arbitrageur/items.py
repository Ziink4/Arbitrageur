from pathlib import Path
from typing import NamedTuple, Optional, List, Dict

from logzero import logger

from arbitrageur.request import request_cached_pages


class ItemUpgrade(NamedTuple):
    upgrade: str
    item_id: int


class Item(NamedTuple):
    id: int
    chat_link: str
    name: str
    icon: Optional[str]
    description: Optional[str]
    type_name: str
    rarity: str
    level: int
    vendor_value: int
    default_skin: Optional[int]
    flags: List[str]
    game_types: List[str]
    restrictions: List[str]
    upgrades_into: Optional[List[ItemUpgrade]]
    upgrades_from: Optional[List[ItemUpgrade]]


def vendor_price(item: Item) -> Optional[int]:
    name = item.name

    if any([name == "Thermocatalytic Reagent",
           name == "Spool of Jute Thread",
           name == "Spool of Wool Thread",
           name == "Spool of Cotton Thread",
           name == "Spool of Linen Thread",
           name == "Spool of Silk Thread",
           name == "Spool of Gossamer Thread",
           (name.endswith("Rune of Holding") and not name.startswith("Supreme")),
           name == "Lump of Tin",
           name == "Lump of Coal",
           name == "Lump of Primordium",
           name == "Jar of Vinegar",
           name == "Packet of Baking Powder",
           name == "Jar of Vegetable Oil",
           name == "Packet of Salt",
           name == "Bag of Sugar",
           name == "Jug of Water",
           name == "Bag of Starch",
           name == "Bag of Flour",
           name == "Bottle of Soy Sauce",
           name == "Milling Basin",
           name == "Crystalline Bottle",
           name == "Bag of Mortar",
           name == "Essence of Elegance"]):
        if item.vendor_value > 0:
            # standard vendor sell price is generally buy price * 8, see:
            # https://forum-en.gw2archive.eu/forum/community/api/How-to-get-the-vendor-sell-price
            return item.vendor_value * 8
        else:
            return None
    elif name == "Pile of Compost Starter":
        return 150
    elif name == "Pile of Powdered Gelatin Mix":
        return 200
    elif name == "Smell-Enhancing Culture":
        return 40000
    elif is_common_ascended_material(item):
        return 0
    else:
        return None


def is_restricted(item: Item) -> bool:
    return any([item.id == 24749,  # legacy Major Rune of the Air
               item.id == 76363,  # legacy catapult schematic
               any(flag == "AccountBound" or flag == "SoulbindOnAcquire" for flag in item.flags)])


def is_common_ascended_material(item: Item) -> bool:
    name = item.name
    return any([name == "Empyreal Fragment",
               name == "Dragonite Ore",
               name == "Pile of Bloodstone Dust"])


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
