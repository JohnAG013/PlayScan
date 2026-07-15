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

PS_LOCALES = {
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
    "IT": "it-it",
    "PL": "pl-pl",
}

# Уровни PS Plus, которые отображаются в карточках товаров
_PS_PLUS_TIERS = {
    "extra": "PS Plus Extra",
    "deluxe": "PS Plus Deluxe",
    "premium": "PS Plus Premium",
    "essential": "PS Plus Essential",
}


def _build_price_patterns(symbol: str) -> list[str]:
    escaped = re.escape(symbol)
    return [
        rf"{escaped}\s*[\d][\d.,]*",
        rf"[\d][\d.,]*\s*{escaped}",
    ]


def _extract_price(text: str, symbol: str) -> tuple[str, float | None]:
    escaped = re.escape(symbol)
    m = re.search(rf"{escaped}\s*([\d][\d.,]*)", text)
    if m:
        return text.strip(), float(m.group(1).replace(",", "."))
    m = re.search(rf"([\d][\d.,]*)\s*{escaped}", text)
    if m:
        return text.strip(), float(m.group(1).replace(",", "."))
    m = re.search(r"([\d]+[.,][\d]+)", text)
    if m:
        return text.strip(), float(m.group(1).replace(",", "."))
    return text.strip(), None


def _detect_platform(text: str) -> str:
    """Определяет платформу из текста карточки.

    PS Store отображает платформы как "PS5 PS4" — приоритет PS5.
    """
    if "PS5" in text:
        return "PS5"
    if "PS4" in text:
        return "PS4"
    return "PS5"


def _detect_subscription(text: str) -> SubscriptionInfo:
    """Определяет подписку PS Plus по расположению ключевых слов в карточке.

    Формат карточки PS Store:
      "Title PS5 PS4 Extra $14.99"
      "Title PS4 Premium $19.99"

    Tier-слово (Extra/Premium/Deluxe) стоит ПОСЛЕ платформы (PS4/PS5),
    но ДО цены. Если слово находится в названии игры — это не подписка.
    """
    # Ищем паттерн: платформа → tier-слово → (цена или конец)
    # Это гарантирует что tier — отдельный элемент карточки, а не часть названия
    for keyword, tier_name in _PS_PLUS_TIERS.items():
        pattern = rf"\bPS[45]\b.*?\b{keyword}\b"
        if re.search(pattern, text, re.I):
            return SubscriptionInfo(
                included_in_subscription=True,
                subscription_name=tier_name,
            )

    return SubscriptionInfo()


class PlayStationParser(BaseParser):
    store_name = "PS Store"

    async def search(self, game_name: str, regions: List[str]) -> List[GameProduct]:
        tasks = [self._search_region(game_name, r) for r in regions]
        batched = await asyncio.gather(*tasks)
        return [item for batch in batched for item in batch]

    async def _search_region(self, game_name: str, region: str) -> List[GameProduct]:
        region = region.upper()
        locale = PS_LOCALES.get(region, "en-us")
        currency, symbol = resolve_currency(region)

        url = f"https://store.playstation.com/{locale}/search/{game_name}"
        headers = {"User-Agent": random_ua(), "Accept-Language": locale}

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("PS Store search [%s] failed: %s", region, exc)
            return []

        return self._parse_html(html, region, currency, symbol)

    def _parse_html(
        self, html: str, region: str, currency: str, symbol: str
    ) -> List[GameProduct]:
        soup = BeautifulSoup(html, "html.parser")
        results: List[GameProduct] = []

        product_links = soup.find_all("a", href=re.compile(r"/product/"))
        seen_urls: set[str] = set()

        for link in product_links:
            href = link.get("href", "")
            if href in seen_urls:
                continue
            seen_urls.add(href)
            product = self._extract_product(link, href, region, currency, symbol)
            if product is not None:
                results.append(product)

        return results

    def _extract_product(
        self, link_tag, href: str, region: str, currency: str, symbol: str
    ) -> GameProduct | None:
        title = link_tag.get_text(strip=True) or link_tag.get("aria-label", "")
        if not title:
            return None

        full_url = f"https://store.playstation.com{href}" if href.startswith("/") else href

        parent = link_tag.find_parent(["div", "li", "section", "article"])
        price_text = "Not Available"
        raw_price = None
        platform = "PS5"
        subscription = SubscriptionInfo()

        if parent:
            full_text = parent.get_text(" ", strip=True)

            # Определяем платформу
            platform = _detect_platform(full_text)

            # Определяем подписку PS Plus
            subscription = _detect_subscription(full_text)

            # Парсим цену
            if re.search(r"\bfree\b|\bбесплатно\b|\bgratis\b", full_text, re.I):
                price_text = "FREE"
                raw_price = 0.0
            else:
                patterns = _build_price_patterns(symbol)
                for pat in patterns:
                    match = re.search(pat, full_text)
                    if match:
                        price_text, raw_price = _extract_price(match.group(), symbol)
                        break

        return GameProduct(
            title=title,
            store_name=self.store_name,
            platform=platform,
            region=region,
            price=price_text,
            raw_price=raw_price,
            currency=currency,
            url=full_url,
            subscription=subscription,
        )
