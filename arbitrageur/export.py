from typing import Dict, List

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from arbitrageur.crafting import ProfitableItem, profit_per_item, profit_on_cost
from arbitrageur.items import Item
from arbitrageur.prices import effective_sell_price
from arbitrageur.recipes import is_time_gated, Recipe

import csv
from logzero import logger


def format_disciplines(disciplines: List[str]) -> str:
    return str(disciplines)[2:-2].replace("', '", "/")


def format_roi(item: ProfitableItem) -> str:
    return f"""{float(profit_on_cost(item)) * 100}%"""


def generate_export_rows(items_map, profitable_items, recipes_map):
    profitable_items = [e for e in profitable_items if e.profit != 0]
    data = []
    for profitable_item in profitable_items:
        item_id = profitable_item.id
        item = items_map[item_id]
        recipe = recipes_map[item_id]

        item_data = {
            'id': item_id,
            'name': item.name,
            'rarity': item.rarity,
            'disciplines': format_disciplines(recipe.disciplines),
            'profit': profitable_item.profit,
            'crafting_cost': profitable_item.crafting_cost,
            'count': profitable_item.count,
            'avg_profit_per_item': profit_per_item(profitable_item),
            'roi': format_roi(profitable_item),
            'link': f"""https://www.gw2bltc.com/en/item/{item.id}""",
            # TODO: This returns the "total" minimal sell price instead of the minimal sell price per item
            'profitability_threshold': effective_sell_price(profitable_item.crafting_cost),
            'time_gated': profitable_item.time_gated,
            'needs_ascended': profitable_item.needs_ascended,
            'craft_level': recipe.min_rating,
        }

        data.append(item_data)
    return data


def export_csv(profitable_items: List[ProfitableItem],
               items_map: Dict[int, Item],
               recipes_map: Dict[int, Recipe]) -> None:
    logger.info("Exporting profitable items as CSV")
    data = generate_export_rows(items_map, profitable_items, recipes_map)
    if len(data) == 0:
        logger.warning("Could not find any profitable item to export")
        return

    with open('export.csv', 'w', newline='') as csvfile:
        datawriter = csv.writer(csvfile, delimiter=',', quotechar='"')
        datawriter.writerow(data[0].keys())

        for item_data in data:
            datawriter.writerow(item_data.values())


def export_excel(profitable_items: List[ProfitableItem],
                 items_map: Dict[int, Item],
                 recipes_map: Dict[int, Recipe]) -> None:
    logger.info("Exporting profitable items as Excel spreadsheet")
    data = generate_export_rows(items_map, profitable_items, recipes_map)
    if len(data) == 0:
        logger.warning("Could not find any profitable item to export")
        return

    wb = Workbook()
    ws = wb.active

    # add column headings. NB. these must be strings
    ws.append(list(data[0].keys()))
    for row in data:
        ws.append(list(row.values()))

    tab = Table(displayName="Data", ref="A1:" + get_column_letter(ws.max_column) + str(ws.max_row))

    # Add a default style with striped rows and banded columns
    style = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False,
                           showLastColumn=False, showRowStripes=True, showColumnStripes=True)
    tab.tableStyleInfo = style

    ws.add_table(tab)
    wb.save("export.xlsx")
