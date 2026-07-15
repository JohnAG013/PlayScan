"""Обертка над PlayFetch для использования в боте PlayScan.

Ищет цены через PlayFetch (Steam, PS, Xbox, GOG, Nintendo)
и возвращает результаты в формате, совместимом с ботом.
"""

import asyncio
import logging

from playfetch import (
    PlayFetchOrchestrator,
    SteamParser,
    PlayStationParser,
    XboxParser,
    GOGParser,
    NintendoParser,
)
from playfetch.models import GameProduct
from database import get_cached_game, cache_game

logger = logging.getLogger(__name__)


def _build_orchestrator() -> PlayFetchOrchestrator:
    return PlayFetchOrchestrator([
        SteamParser(),
        PlayStationParser(),
        XboxParser(),
        GOGParser(),
        NintendoParser(),
    ])


def _region_to_playfetch(user_region: str) -> list[str]:
    """Конвертирует регион бота (us, de, ru) в формат PlayFetch (US, DE, RU)."""
    mapping = {
        "global": ["US", "TR"],
        "us": ["US"],
        "gb": ["GB"],
        "de": ["DE"],
        "fr": ["FR"],
        "it": ["IT"],
        "es": ["ES"],
        "ru": ["RU"],
        "ua": ["UA"],
        "kz": ["KZ"],
        "tr": ["TR"],
        "pl": ["PL"],
        "cz": ["CZ"],
        "jp": ["JP"],
        "kr": ["KR"],
        "br": ["BR"],
        "au": ["AU"],
        "ca": ["CA"],
        "in": ["IN"],
        "ar": ["AR"],
        "nl": ["NL"],
        "pt": ["PT"],
        "se": ["SE"],
        "no": ["NO"],
        "dk": ["DK"],
        "fi": ["FI"],
    }
    return mapping.get(user_region.lower(), ["US"])


def _platform_to_playfetch(device: str) -> list[str]:
    """Конвертирует платформу бота в формат PlayFetch."""
    mapping = {
        "all": ["PC", "PS5", "PS4", "Xbox Series X|S", "Xbox One", "Switch"],
        "pc": ["PC"],
        "ps": ["PS5", "PS4"],
        "xbox": ["Xbox Series X|S", "Xbox One"],
        "nintendo": ["Switch"],
    }
    return mapping.get(device.lower(), ["PC", "PS5", "Xbox Series X|S"])


def _product_to_deal(product: GameProduct) -> dict:
    """Конвертирует GameProduct из PlayFetch в формат deal бота."""
    platform_map = {
        "PC": "pc",
        "PS5": "ps",
        "PS4": "ps",
        "Xbox Series X|S": "xbox",
        "Xbox One": "xbox",
        "Switch": "nintendo",
    }

    deal = {
        "title": product.title,
        "price_usd": f"{product.raw_price:.2f}" if product.raw_price is not None else "?",
        "price_converted": None,
        "currency": product.currency,
        "normal_price": "?",
        "savings": 0,
        "store": product.store_name,
        "platform": platform_map.get(product.platform, "pc"),
        "link": product.url,
        "game_link": product.url,
        "metacritic": None,
    }

    # Добавляем информацию о подписке
    if product.subscription.included_in_subscription:
        deal["subscription"] = product.subscription.subscription_name

    return deal


async def search_playfetch(
    query: str,
    user_region: str = "us",
    device: str = "all",
    target_currency: str = "USD",
) -> list[dict]:
    """Поиск через PlayFetch.

    Возвращает список сделок в формате бота.
    """
    regions = _region_to_playfetch(user_region)
    platforms = _platform_to_playfetch(device)

    # Проверяем кэш в Google Sheets для каждого региона и платформы
    cached_deals = []
    for region in regions:
        for platform in platforms:
            cached = await get_cached_game(query, "PlayFetch", region, platform)
            if cached:
                deal = {
                    "title": cached["title"],
                    "price_usd": f"{cached['raw_price']:.2f}" if cached["raw_price"] else "?",
                    "price_converted": None,
                    "currency": cached["currency"],
                    "normal_price": "?",
                    "savings": 0,
                    "store": cached["store"],
                    "platform": _platform_to_bot(platform),
                    "link": cached["url"],
                    "game_link": cached["url"],
                    "metacritic": None,
                }
                cached_deals.append(deal)

    if cached_deals:
        logger.info(f"Google Sheets cache hit: {query}")
        return cached_deals

    # Если нет в кэше — ищем через PlayFetch
    orch = _build_orchestrator()

    try:
        products = await asyncio.wait_for(
            orch.search_everywhere(query, regions, platforms),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning(f"PlayFetch timeout for {query}")
        return []
    except Exception as e:
        logger.error(f"PlayFetch error for {query}: {e}")
        return []

    deals = [_product_to_deal(p) for p in products]

    # Сохраняем в кэш Google Sheets
    for deal in deals:
        platform_db = _platform_to_db(deal["platform"])
        await cache_game(
            game_name=query,
            store=deal["store"],
            region=user_region.upper(),
            platform=platform_db,
            title=deal["title"],
            price=deal["price_usd"],
            raw_price=float(deal["price_usd"]) if deal["price_usd"] not in ("?", "", None) else None,
            currency=deal["currency"],
            url=deal["link"],
        )

    # Сортируем по цене
    deals.sort(
        key=lambda x: float(x["price_usd"]) if x["price_usd"] not in ("?", "", None) else 9999
    )

    return deals


def _platform_to_bot(platform: str) -> str:
    """Конвертирует платформу PlayFetch в формат бота."""
    mapping = {
        "PC": "pc",
        "PS5": "ps",
        "PS4": "ps",
        "Xbox Series X|S": "xbox",
        "Xbox One": "xbox",
        "Switch": "nintendo",
    }
    return mapping.get(platform, "pc")


def _platform_to_db(platform: str) -> str:
    """Конвертирует платформу бота в формат для БД."""
    mapping = {
        "pc": "PC",
        "ps": "PS5",
        "xbox": "Xbox Series X|S",
        "nintendo": "Switch",
    }
    return mapping.get(platform, "PC")
