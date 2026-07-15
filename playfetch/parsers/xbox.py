import asyncio
import json
import logging
import re
from typing import List

import httpx

from playfetch.base import BaseParser
from playfetch.models import GameProduct, SubscriptionInfo, resolve_currency
from playfetch.utils import random_ua

logger = logging.getLogger(__name__)

XBOX_LOCALES = {
    "US": "en-us",
    "GB": "en-gb",
    "EU": "de-de",
    "RU": "ru-ru",
    "TR": "tr-tr",
    "KZ": "ru-ru",
    "JP": "ja-jp",
    "KR": "ko-kr",
    "BR": "pt-br",
    "AU": "en-au",
    "CA": "en-ca",
    "MX": "es-mx",
    "IN": "en-in",
    "DE": "de-de",
    "FR": "fr-fr",
    "ES": "es-es",
    "PL": "pl-pl",
}

_GAME_PASS_IDS = {
    "CFQ7TTC0K6L8": "Xbox Game Pass",
    "CFQ7TTC0KGQ8": "PC Game Pass",
    "CFQ7TTC0P85B": "Xbox Game Pass Premium",
    "CFQ7TTC0KHS0": "Xbox Game Pass Ultimate",
}


def _extract_products_from_html(html: str) -> list[dict]:
    """Извлекает данные товаров из JSON в HTML поиска Xbox.

    Xbox.com хранит данные поиска в script-тегах как JSON.
    Каждый товар содержит: title, listPrice, msrp, passMetadataByPassProductId.
    """
    products = []

    # Ищем паттерн: "title":"..." ... "listPrice":N ... "passMetadataByPassProductId":{...}
    # Xbox оборачивает каждый товар в JSON объект с productId, title, и ценовыми данными

    # Паттерн 1: Извлекаем полные product objects из JSON
    # Формат: "productId":"9P...","title":"...",..."listPrice":N,...,"passMetadataByPassProductId":{...}
    pattern = r'"productId"\s*:\s*"(9P[A-Z0-9]+)".*?"title"\s*:\s*"([^"]+)".*?"listPrice"\s*:\s*([\d.]+).*?"msrp"\s*:\s*([\d.]+).*?"currency"\s*:\s*"([A-Z]+)"'

    for m in re.finditer(pattern, html, re.DOTALL):
        pid, title, list_price, msrp, currency = m.group(1), m.group(2), float(m.group(3)), float(m.group(4)), m.group(5)

        # Проверяем, есть ли passMetadataByPassProductId рядом (в пределах 2000 символов)
        start_pos = m.end()
        chunk = html[start_pos:start_pos + 2000]
        has_gp = bool(re.search(r"passMetadataByPassProductId", chunk))
        gp_name = None
        if has_gp:
            for gp_id, gp_label in _GAME_PASS_IDS.items():
                if gp_id in chunk[:500]:
                    gp_name = gp_label
                    break
            if not gp_name:
                gp_name = "Xbox Game Pass"

        # Платформа
        platform_chunk = html[max(0, m.start() - 500):m.start()]
        if "XboxOne" in platform_chunk or "Xbox One" in platform_chunk:
            platform = "Xbox One"
        else:
            platform = "Xbox Series X|S"

        products.append({
            "product_id": pid,
            "title": title,
            "list_price": list_price,
            "msrp": msrp,
            "currency": currency,
            "platform": platform,
            "has_game_pass": has_gp,
            "game_pass_name": gp_name,
            "url": f"https://www.xbox.com/en-us/games/store/{pid}",
        })

    # Дедупликация по product_id
    seen = set()
    unique = []
    for p in products:
        if p["product_id"] not in seen:
            seen.add(p["product_id"])
            unique.append(p)

    return unique


class XboxParser(BaseParser):
    store_name = "Xbox Store"

    async def search(self, game_name: str, regions: List[str]) -> List[GameProduct]:
        tasks = [self._search_region(game_name, r) for r in regions]
        batched = await asyncio.gather(*tasks)
        return [item for batch in batched for item in batch]

    async def _search_region(self, game_name: str, region: str) -> List[GameProduct]:
        region = region.upper()
        locale = XBOX_LOCALES.get(region, "en-us")
        currency, symbol = resolve_currency(region)

        url = f"https://www.xbox.com/{locale}/search/results?q={game_name}"
        headers = {"User-Agent": random_ua(), "Accept-Language": locale}

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Xbox Store search [%s] failed: %s", region, exc)
            return []

        raw_products = _extract_products_from_html(html)

        results = []
        for p in raw_products:
            # Определяем цену
            list_price = p["list_price"]
            if list_price == 0:
                price_text = "FREE"
                raw_price = 0.0
            elif list_price > 0:
                price_text = f"{symbol}{list_price:.2f}"
                raw_price = list_price
            else:
                price_text = "Not Available"
                raw_price = None

            # Определяем подписку
            subscription = SubscriptionInfo()
            if p["has_game_pass"]:
                subscription = SubscriptionInfo(
                    included_in_subscription=True,
                    subscription_name=p["game_pass_name"] or "Xbox Game Pass",
                )

            # URL товара
            product_url = f"https://www.xbox.com/{locale}/games/store/{p['product_id']}"

            results.append(GameProduct(
                title=p["title"],
                store_name=self.store_name,
                platform=p["platform"],
                region=region,
                price=price_text,
                raw_price=raw_price,
                currency=currency,
                url=product_url,
                subscription=subscription,
            ))

        return results
