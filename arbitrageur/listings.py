from dataclasses import dataclass
from typing import List, Optional

from arbitrageur.prices import effective_buy_price


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

    def buy(self, count: int) -> Optional[int]:
        cost = 0
        while count > 0:
            if len(self.sells) == 0:
                return None

            # sells are sorted in descending price
            self.sells[-1].quantity -= 1
            count -= 1
            cost += self.sells[-1].unit_price

            if self.sells[-1].quantity == 0:
                self.sells.pop()

        return cost

    def sell(self) -> Optional[int]:
        if len(self.buys) == 0:
            return None

        revenue = 0
        # buys are sorted in ascending price
        self.buys[-1].quantity -= 1
        revenue += effective_buy_price(self.buys[-1].unit_price)

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
