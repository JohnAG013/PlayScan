"""Обертка над PlayFetch для использования в боте PlayScan.

Ищет цены через PlayFetch (Steam, PS, Xbox, GOG, Nintendo)
и возвращает результаты в формате, совместимом с ботом.
"""

import asyncio
import logging
import time
import json
from pathlib import Path

from playfetch import (
    PlayFetchOrchestrator,
    SteamParser,
    PlayStationParser,
    XboxParser,
    GOGParser,
    NintendoParser,
)
from playfetch.models import GameProduct

logger = logging.getLogger(__name__)

# Кэш на 24 часа
_CACHE_TTL = 24 * 60 * 60
_cache: dict[str, dict] = {}
_CACHE_FILE = Path("playfetch_cache.json")


def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning(f"Failed to save cache: {e}")


def _get_cached(key: str) -> list[dict] | None:
    entry = _cache.get(key)
    if not entry:
        return None
    ts = entry.get("timestamp", 0)
    if time.time() - ts > _CACHE_TTL:
        return None
    return entry.get("data")


def _set_cached(key: str, data: list[dict]) -> None:
    _cache[key] = {"timestamp": time.time(), "data": data}
    _save_cache(_cache)


# Загружаем кэш при старте
_cache = _load_cache()


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
    cache_key = f"pf|{query.lower()}|{user_region}|{device}"
    cached = _get_cached(cache_key)
    if cached is not None:
        logger.info(f"PlayFetch cache hit: {query}")
        return cached

    regions = _region_to_playfetch(user_region)
    platforms = _platform_to_playfetch(device)

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

    # Сортируем по цене
    deals.sort(
        key=lambda x: float(x["price_usd"]) if x["price_usd"] not in ("?", "", None) else 9999
    )

    if deals:
        _set_cached(cache_key, deals)

    return deals
