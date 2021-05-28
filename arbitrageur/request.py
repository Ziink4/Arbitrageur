import json
from pathlib import Path
from typing import List, Any, Tuple

import aiohttp
import asyncio

MAX_PAGE_SIZE = 200  # See: https://wiki.guildwars2.com/wiki/API:2#Paging
MAX_ITEM_ID_LENGTH = 200  # Error returned for greater than this amount


async def request_item_ids(url_path: str, item_ids: List[int]) -> List[Any]:
    result = []

    async with aiohttp.ClientSession() as session:
        for batch in [item_ids[i:i + MAX_ITEM_ID_LENGTH] for i in range(0, len(item_ids), MAX_ITEM_ID_LENGTH)]:
            item_ids_str = map(str, batch)

            url = f"""https://api.guildwars2.com/v2/{url_path}?ids={",".join(item_ids_str)}"""
            print(f"""Fetching {url}""")

            async with session.get(url) as response:
                result.append(await response.json())

    return result


async def fetch_item_listings(item_ids: List[int]) -> List[Any]:
    tp_listings = await request_item_ids("commerce/listings", item_ids)

    for listings in tp_listings:
        assert len(listings) == 1
        listings_dict = listings[0]

        # by default sells are listed in ascending and buys in descending price.
        # reverse lists to allow best offers to be popped instead of spliced from front.
        assert "id" in listings_dict
        assert "buys" in listings_dict
        assert "sells" in listings_dict
        listings_dict["buys"].reverse()
        listings_dict["sells"].reverse()

    return tp_listings


async def request_page(url_path: str, page_no: int) -> Tuple[int, Any]:
    url = f"""https://api.guildwars2.com/v2/{url_path}?page={page_no}&page_size={MAX_PAGE_SIZE}"""
    print(f"""Fetching {url}""")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            assert "X-Page-Total" in response.headers
            page_total_str = response.headers.get("X-Page-Total")
            page_total = int(page_total_str)
            return page_total, await response.json()


async def request_all_pages(url_path: str):
    # update page total with first request
    page_total, items = await request_page(url_path, page_no=0)

    tasks = [request_page(url_path, page_no) for page_no in range(1, page_total)]
    results = await asyncio.gather(*tasks)

    for _, items_in_page in results:
        items += items_in_page

    return items


async def request_cached_pages(cache_path: Path, url_path: str):
    if cache_path.is_file():
        with open(cache_path) as cache_file:
            print(f"""Loading page cache for "{url_path}" """)
            return json.load(cache_file)

    items = await request_all_pages(url_path)

    with open(cache_path, "w") as cache_file:
        print(f"""Saving page cache for "{url_path}" """)
        json.dump(items, cache_file)

    return items


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Test item listings
    # result = loop.run_until_complete(fetch_item_listings([3645, 123]))
    # print(result)

    # Test request page
    # result = loop.run_until_complete(request_page("commerce/prices", 1))
    # print(result)

    # Test request all pages
    # result = loop.run_until_complete(request_all_pages("commerce/prices"))
    # print(result)

    # Test request cached pages
    result = loop.run_until_complete(request_cached_pages(Path("prices.json"), "commerce/prices"))
    # print(result)
