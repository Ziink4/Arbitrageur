from math import floor
from typing import NamedTuple

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


if __name__ == "__main__":
    # Test effective buy price
    p = Price(143, PriceInfo(12, 1), PriceInfo(0, 0))
    logger.info(p)
    ep = effective_buy_price(p.buys.unit_price)
    logger.info(ep)
