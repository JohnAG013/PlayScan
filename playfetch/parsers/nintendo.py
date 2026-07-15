import asyncio
import logging
import re
from typing import List

import httpx

from playfetch.base import BaseParser
from playfetch.models import GameProduct, SubscriptionInfo, resolve_currency
from playfetch.utils import random_ua

logger = logging.getLogger(__name__)

_ALGOLIA_URL = "https://search.nintendo-europe.com/en/select"


class NintendoParser(BaseParser):
    """Парсер Nintendo eShop через Algolia Search API.

    Быстрый и стабильный API. Цены в EUR для европейских регионов.
    """
    store_name = "Nintendo"

    async def search(self, game_name: str, regions: List[str]) -> List[GameProduct]:
        tasks = [self._search_region(game_name, r) for r in regions]
        batched = await asyncio.gather(*tasks)
        return [item for batch in batched for item in batch]

    async def _search_region(self, game_name: str, region: str) -> List[GameProduct]:
        region = region.upper()
        # Nintendo Europe Algolia API возвращает EUR
        currency, symbol = resolve_currency(region)

        params = {
            "q": game_name,
            "fq": "type:GAME",
            "wt": "json",
            "rows": 10,
        }
        headers = {"User-Agent": random_ua()}

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(_ALGOLIA_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Nintendo search [%s] failed: %s", region, exc)
            return []

        docs = data.get("response", {}).get("docs", [])
        results = []
        for doc in docs:
            product = self._to_product(doc, region, currency, symbol)
            if product is not None:
                results.append(product)
        return results

    def _to_product(self, doc: dict, region: str, currency: str, symbol: str) -> GameProduct | None:
        title = doc.get("title", "")
        if not title or len(title) < 2:
            return None

        # Algolia возвращает цену в price_lowest_f (с учётом скидок) или price_sorting_f
        price_lowest = doc.get("price_lowest_f")
        price_sorting = doc.get("price_sorting_f")
        discount_pct = doc.get("price_discount_percentage_f", 0)

        # -1 означает "нет цены" (免费 или не продаётся)
        if price_lowest is not None and price_lowest > 0:
            raw_price = float(price_lowest)
            price_text = f"{symbol}{raw_price:.2f}"
        elif price_sorting is not None and price_sorting > 0 and price_sorting < 999999:
            raw_price = float(price_sorting)
            price_text = f"{symbol}{raw_price:.2f}"
        else:
            price_text = "Not Available"
            raw_price = None

        # URL игры
        url_path = doc.get("url", "")
        url = f"https://www.nintendo.com{url_path}" if url_path.startswith("/") else url_path

        # Платформа
        systems = doc.get("system_type", [])
        platform = "Switch"
        for s in systems:
            if "switch" in s.lower():
                platform = "Switch"
                break

        return GameProduct(
            title=title,
            store_name=self.store_name,
            platform=platform,
            region=region,
            price=price_text,
            raw_price=raw_price,
            currency=currency,
            url=url,
        )
