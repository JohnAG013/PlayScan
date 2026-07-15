import asyncio
import logging
import re
from typing import List

import httpx
from bs4 import BeautifulSoup

from playfetch.base import BaseParser
from playfetch.models import GameProduct, SubscriptionInfo, resolve_currency
from playfetch.utils import random_ua

logger = logging.getLogger(__name__)


class GOGParser(BaseParser):
    """Парсер GOG.com.

    GOG embed API возвращает 0 продуктов. Парсим HTML через BeautifulSoup.
    GOG отдаёт данные в тексте ссылок: "Title-90%$10.95$1.09"
    GOG продаёт все игры в USD (не поддерживает региональные цены).
    """
    store_name = "GOG"

    async def search(self, game_name: str, regions: List[str]) -> List[GameProduct]:
        # GOG не зависит от региона — все цены в USD
        url = f"https://www.gog.com/en/games?search={game_name}&sort=popularity"
        headers = {"User-Agent": random_ua()}

        try:
            async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("GOG search failed: %s", exc)
            return []

        return self._parse_html(html)

    def _parse_html(self, html: str) -> List[GameProduct]:
        """Парсим HTML-страницу поиска GOG.

        GOG отдаёт карточки товаров как ссылки <a href="/en/game/slug">,
        текст ссылки содержит название, скидку и цену:
        "Hitman: Blood Money -90% $10.95 $1.09"
        """
        soup = BeautifulSoup(html, "html.parser")
        results: List[GameProduct] = []

        # GOG карточки — ссылки вида /en/game/slug
        links = soup.find_all("a", href=re.compile(r"/en/game/"))
        seen_urls: set[str] = set()

        for link in links:
            href = link.get("href", "")
            if href in seen_urls:
                continue
            seen_urls.add(href)

            product = self._extract_product(link, href)
            if product is not None:
                results.append(product)

        return results

    def _extract_product(self, link_tag, href: str) -> GameProduct | None:
        """Извлекает данные товара из ссылки GOG.

        Формат текста: "Title -90% $10.95 $1.09" или "Title $59.99"
        """
        full_url = f"https://www.gog.com{href}" if href.startswith("/") else href

        # Получаем полный текст ссылки
        full_text = link_tag.get_text(" ", strip=True)

        # Извлекаем название — всё до первого процента или цены
        title_match = re.match(r"^(.+?)(?:\s*-\d+%|\s*\$)", full_text)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title = full_text[:60].strip()

        if not title or len(title) < 2:
            return None

        # GOG всегда возвращает USD
        currency, symbol = "USD", "$"

        # Извлекаем цены (все $XX.XX из текста)
        prices = re.findall(r"\$([\d,]+\.?\d*)", full_text)

        if not prices:
            price_text = "Not Available"
            raw_price = None
        else:
            # Последняя цена — финальная (со скидкой)
            raw_price = float(prices[-1].replace(",", ""))
            if raw_price == 0:
                price_text = "FREE"
            else:
                price_text = f"{symbol}{raw_price:.2f}"

        return GameProduct(
            title=title,
            store_name=self.store_name,
            platform="PC",
            region="US",
            price=price_text,
            raw_price=raw_price,
            currency=currency,
            url=full_url,
        )
