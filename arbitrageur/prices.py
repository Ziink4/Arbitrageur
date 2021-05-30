from math import floor
from typing import NamedTuple, Dict

from logzero import logger

from arbitrageur.request import request_all_pages

TRADING_POST_COMMISSION = 0.15


class PriceInfo(NamedTuple):
    unit_price: int
    quantity: int


class Price(NamedTuple):
    id: int
    buys: PriceInfo
    sells: PriceInfo


def effective_buy_price(unit_price: int) -> int:
    return floor(unit_price * (1.0 - TRADING_POST_COMMISSION))


def effective_sell_price(unit_price: int) -> int:
    return floor(unit_price / (1.0 - TRADING_POST_COMMISSION))


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


if __name__ == "__main__":
    # Test effective buy price
    p = Price(143, PriceInfo(12, 1), PriceInfo(0, 0))
    logger.info(p)
    ep = effective_buy_price(p.buys.unit_price)
    logger.info(ep)
