import asyncio
import logging
from typing import List

import httpx

from playfetch.base import BaseParser
from playfetch.models import GameProduct, SubscriptionInfo, resolve_currency
from playfetch.utils import random_ua

logger = logging.getLogger(__name__)

_STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"


class SteamParser(BaseParser):
    """Парсер Steam.

    ВАЖНО: l=english всегда, чтобы названия были на английском и не ломали верстку.
    cc={region} — принудительно задаёт регион для цен.
    """
    store_name = "Steam"

    async def search(self, game_name: str, regions: List[str]) -> List[GameProduct]:
        tasks = [self._search_region(game_name, r) for r in regions]
        batched = await asyncio.gather(*tasks)
        return [item for batch in batched for item in batch]

    async def _search_region(self, game_name: str, region: str) -> List[GameProduct]:
        region = region.upper()
        _, symbol = resolve_currency(region)
        headers = {"User-Agent": random_ua()}
        params = {
            "term": game_name,
            "l": "english",  # Всегда английский для названий
            "cc": region,     # Принудительно регион для цен
        }

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(_STEAM_SEARCH_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Steam search [%s] failed: %s", region, exc)
            return []

        items = data.get("items", [])
        return [self._to_product(item, region) for item in items]

    def _to_product(self, item: dict, region: str) -> GameProduct:
        title = item.get("name", "")
        app_id = item.get("id")
        url = f"https://store.steampowered.com/app/{app_id}"

        price_info = item.get("price", {})
        final_price = price_info.get("final", 0)
        currency, symbol = resolve_currency(region)

        is_free = item.get("is_free", False)
        if is_free:
            price_text = "FREE"
            raw_price = 0.0
        elif final_price > 0:
            raw_price = final_price / 100
            price_text = f"{symbol}{raw_price:.2f}"
        else:
            price_text = "Not Available"
            raw_price = None

        return GameProduct(
            title=title,
            store_name=self.store_name,
            platform="PC",
            region=region,
            price=price_text,
            raw_price=raw_price,
            currency=currency,
            url=url,
        )
