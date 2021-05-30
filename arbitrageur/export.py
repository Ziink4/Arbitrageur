from typing import Dict, List

from arbitrageur.crafting import ProfitableItem
from arbitrageur.items import Item
from arbitrageur.prices import effective_sell_price
from arbitrageur.recipes import is_time_gated, Recipe

import csv
from logzero import logger


def handle_disciplines(disciplines: List[str]):
    return str(disciplines)[2:-2].replace("', '", "/")


def export_csv(profitable_items: List[ProfitableItem], item_map: Dict[int, Item], recipes_map: Dict[int, Recipe]):
    data = []
    profitable_items = [e for e in profitable_items if e.profit != 0]

    for item in profitable_items:
        item_data = {
            'name':                    item_map[item.id].name,
            'disciplines':             handle_disciplines(recipes_map[item.id].disciplines),
            'profit':                  item.profit,
            'count':                   item.count,
            'link':                    f'https://www.gw2bltc.com/en/item/{item.id}',
            'id':                      item.id,
            'profitability_threshold': effective_sell_price(item.crafting_cost),
            'timegated':               is_time_gated(recipes_map[item.id]),
            'craft_level':             recipes_map[item.id].min_rating,
        }

        data.append(item_data)

    with open('output.csv', 'w', newline='') as csvfile:
        datawriter = csv.writer(csvfile, delimiter=',', quotechar='"')
        datawriter.writerow(data[0].keys())

        for item_data in data:
            datawriter.writerow(item_data.values())
