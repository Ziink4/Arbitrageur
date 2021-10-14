import json
from pathlib import Path
from typing import List, Any, Tuple, Optional

import aiohttp
import asyncio
from logzero import logger

MAX_PAGE_SIZE = 200  # See: https://wiki.guildwars2.com/wiki/API:2#Paging
MAX_ITEM_ID_LENGTH = 200  # Error returned for greater than this amount


async def request_item_ids(url_path: str, item_ids: List[int]) -> List[Any]:
    result = []

    async with aiohttp.ClientSession() as session:
        for batch in [item_ids[i:i + MAX_ITEM_ID_LENGTH] for i in range(0, len(item_ids), MAX_ITEM_ID_LENGTH)]:
            item_ids_str = map(str, batch)

            url = f"""https://api.guildwars2.com/v2/{url_path}?ids={",".join(item_ids_str)}"""
            logger.info(f"""Fetching {url}""")

            async with session.get(url) as response:
                response_json = await response.json()

            result.extend(response_json)

    return result


async def fetch_item_listings(item_ids: List[int]) -> List[Any]:
    tp_listings = await request_item_ids("commerce/listings", item_ids)

    for listings in tp_listings:
        # by default sells are listed in ascending and buys in descending price.
        # reverse lists to allow best offers to be popped instead of spliced from front.
        listings["buys"].reverse()
        listings["sells"].reverse()

    return tp_listings


async def request_page(url_path: str, page_no: int) -> Tuple[Optional[int], Any]:
    url = f"""https://api.guildwars2.com/v2/{url_path}?page={page_no}&page_size={MAX_PAGE_SIZE}"""
    logger.info(f"""Fetching {url}""")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            page_total = None
            if page_no == 0:
                assert "X-Page-Total" in response.headers, f"""First page of {url_path} is missing page count, please retry later """
                page_total_str = response.headers.get("X-Page-Total")
                page_total = int(page_total_str)

            data = await response.json()
            if "text" in data:
                return page_total, []

            return page_total, data


async def request_all_pages(url_path: str):
    # update page total with first request
    page_total, items = await request_page(url_path, page_no=0)

    # try fetching one extra page in case page total increased while paginating
    tasks = [request_page(url_path, page_no) for page_no in range(1, page_total + 1)]
    results = await asyncio.gather(*tasks)

    for _, items_in_page in results:
        items += items_in_page

    return items


async def request_cached_pages(cache_path: Path, url_path: str):
    if cache_path.is_file():
        with open(cache_path) as cache_file:
            logger.info(f"""Loading page cache for "{url_path}" """)
            return json.load(cache_file)

    items = await request_all_pages(url_path)

    with open(cache_path, "w") as cache_file:
        logger.info(f"""Saving page cache for "{url_path}" """)
        json.dump(items, cache_file)

    return items


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Test item listings
    # result = loop.run_until_complete(fetch_item_listings([3645, 123]))
    # logger.info(result)

    # Test request page
    # result = loop.run_until_complete(request_page("commerce/prices", 1))
    # logger.info(result)

    # Test request all pages
    # result = loop.run_until_complete(request_all_pages("commerce/prices"))
    # logger.info(result)

    # Test request cached pages
    result = loop.run_until_complete(request_cached_pages(Path("prices.json"), "commerce/prices"))
    # logger.info(result)
