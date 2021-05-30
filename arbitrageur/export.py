from typing import Dict, List

from arbitrageur.crafting import ProfitableItem, profit_per_item, profit_on_cost
from arbitrageur.items import Item
from arbitrageur.prices import effective_sell_price
from arbitrageur.recipes import is_time_gated, Recipe

import csv
from logzero import logger


def format_disciplines(disciplines: List[str]) -> str:
    return str(disciplines)[2:-2].replace("', '", "/")


def format_roi(item: ProfitableItem) -> str:
    return f"""{profit_on_cost(item) * 100}%"""


def export_csv(profitable_items: List[ProfitableItem],
               items_map: Dict[int, Item],
               recipes_map: Dict[int, Recipe]) -> None:
    profitable_items = [e for e in profitable_items if e.profit != 0]
    if len(profitable_items) == 0:
        logger.warning("Could not find any profitable item to export")
        return

    data = []

    for profitable_item in profitable_items:
        item_id = item.id
        item = items_map[item_id]
        recipe = recipes_map[item_id]

        item_data = {
            'name': item.name,
            'disciplines': format_disciplines(recipe.disciplines),
            'profit': profitable_item.profit,
            'crafting_cost': profitable_item.crafting_cost,
            'count': item.count,
            'avg_profit_per_item': profit_per_item(profitable_item),
            'roi': format_roi(profitable_item),
            'link': f"""https://www.gw2bltc.com/en/item/{item.id}""",
            'id': item.id,
            'profitability_threshold': effective_sell_price(profitable_item.crafting_cost),
            'time_gated': is_time_gated(recipe),
            'craft_level': recipe.min_rating,
        }

        data.append(item_data)

    with open('output.csv', 'w', newline='') as csvfile:
        datawriter = csv.writer(csvfile, delimiter=',', quotechar='"')
        datawriter.writerow(data[0].keys())

        for item_data in data:
            datawriter.writerow(item_data.values())
