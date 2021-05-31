from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

from logzero import logger

from arbitrageur.prices import effective_buy_price
from arbitrageur.request import fetch_item_listings


@dataclass
class Listing:
    listings: int
    unit_price: int
    quantity: int


@dataclass
class ItemListings:
    id: int
    buys: List[Listing]
    sells: List[Listing]

    def buy(self, count: int) -> Optional[Tuple[int, Dict[int, int]]]:
        cost = 0
        listings = {}
        while count > 0:
            if len(self.sells) == 0:
                return None

            # sells are sorted in descending price
            self.sells[-1].quantity -= 1
            count -= 1
            unit_price = self.sells[-1].unit_price
            cost += unit_price

            if unit_price in listings:
                listings[unit_price] += 1
            else:
                listings[unit_price] = 1

            if self.sells[-1].quantity == 0:
                self.sells.pop()

        return cost, listings

    def sell(self) -> Optional[int]:
        if len(self.buys) == 0:
            return None

        # buys are sorted in ascending price
        self.buys[-1].quantity -= 1
        revenue = self.buys[-1].unit_price

        if self.buys[-1].quantity == 0:
            self.buys.pop()

        return revenue

    def lowest_sell_offer(self, count: int) -> Optional[int]:
        cost = 0

        for listing in reversed(self.sells):
            if listing.quantity < count:
                count -= listing.quantity
                cost += listing.unit_price * listing.quantity
            else:
                cost += listing.unit_price * count
                count = 0

            if count == 0:
                break

        if count > 0:
            return None

        return cost


async def retrieve_detailed_tp_listings(item_ids: List[int]) -> Dict[int, ItemListings]:
    logger.info("Loading detailed trading post listings")
    tp_listings = await fetch_item_listings(item_ids)
    logger.info(f"""Loaded {len(tp_listings)} detailed trading post listings""")
    logger.info("Parsing detailed trading post listings data")
    tp_listings_map = {listings["id"]: ItemListings(id=listings["id"],
                                                    buys=[Listing(listings=listing["listings"],
                                                                  unit_price=listing["unit_price"],
                                                                  quantity=listing["quantity"]) for listing in
                                                          listings["buys"]],
                                                    sells=[Listing(listings=listing["listings"],
                                                                   unit_price=listing["unit_price"],
                                                                   quantity=listing["quantity"]) for listing in
                                                           listings["sells"]]) for listings in tp_listings}
    return tp_listings_map
