import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List

from playfetch.base import BaseParser
from playfetch.models import GameProduct
from playfetch.fuzzy import fuzzy_filter

logger = logging.getLogger(__name__)

PLATFORM_PARSER_MAP = {
    "PC": ["SteamParser", "GOGParser"],
    "PS": ["PlayStationParser"],
    "PS4": ["PlayStationParser"],
    "PS5": ["PlayStationParser"],
    "Xbox": ["XboxParser"],
    "Xbox One": ["XboxParser"],
    "Xbox Series X|S": ["XboxParser"],
    "Switch": ["NintendoParser"],
}

# Время жизни кэша — 24 часа
_CACHE_TTL = 24 * 60 * 60
_CACHE_FILE = Path("local_cache.json")


class PlayFetchOrchestrator:
    def __init__(self, parsers: List[BaseParser], cache_file: Path | None = None):
        if not parsers:
            raise ValueError("Нужен хотя бы один парсер")
        self._parsers = parsers
        self._by_name = {type(p).__name__: p for p in parsers}
        self._cache_file = cache_file or _CACHE_FILE
        self._cache: dict = self._load_cache()

    def _load_cache(self) -> dict:
        """Загружает кэш из файла."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_cache(self) -> None:
        """Сохраняет кэш в файл."""
        try:
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Failed to save cache: %s", exc)

    def _cache_key(self, game_name: str, platforms: List[str], regions: List[str]) -> str:
        """Генерирует ключ кэша."""
        return f"{game_name.lower()}|{'|'.join(sorted(p for p in platforms))}|{'|'.join(sorted(r for r in regions))}"

    def _get_cached(self, key: str) -> List[GameProduct] | None:
        """Получает данные из кэша, если они не устарели."""
        entry = self._cache.get(key)
        if not entry:
            return None
        ts = entry.get("timestamp", 0)
        if time.time() - ts > _CACHE_TTL:
            return None
        try:
            return [GameProduct(**item) for item in entry.get("data", [])]
        except Exception:
            return None

    def _set_cached(self, key: str, data: List[GameProduct]) -> None:
        """Записывает данные в кэш."""
        self._cache[key] = {
            "timestamp": time.time(),
            "data": [p.model_dump(mode="json") for p in data],
        }
        self._save_cache()

    async def search_all(
        self, game_name: str, platforms: List[str], regions: List[str]
    ) -> str:
        all_products = await self._search(game_name, platforms, regions)
        return json.dumps(
            [p.model_dump(mode="json") for p in all_products],
            ensure_ascii=False,
            indent=4,
        )

    async def search_everywhere(
        self, game_name: str, regions: List[str], platforms: List[str] | None = None
    ) -> List[GameProduct]:
        return await self._search(game_name, platforms, regions)

    async def _search(
        self, game_name: str, platforms: List[str] | None, regions: List[str]
    ) -> List[GameProduct]:
        # Проверяем кэш
        key = self._cache_key(game_name, platforms or [], regions)
        cached = self._get_cached(key)
        if cached is not None:
            logger.info("Cache hit for '%s'", game_name)
            return cached

        # Определяем какие парсеры запускать
        parser_names: set[str] = set()
        if platforms:
            for plat in platforms:
                names = PLATFORM_PARSER_MAP.get(plat, [])
                for name in names:
                    if name in self._by_name:
                        parser_names.add(name)
        if not parser_names:
            parser_names = set(self._by_name.keys())

        tasks = [
            self._safe_search(self._by_name[name], game_name, regions)
            for name in parser_names
        ]
        raw_results = await asyncio.gather(*tasks)
        all_products = [item for batch in raw_results for item in batch]

        # Fuzzy-фильтрация
        all_products = fuzzy_filter(all_products, game_name, threshold=0.55)

        # Сортировка
        def sort_key(p: GameProduct) -> tuple[int, float]:
            if p.raw_price is None:
                return (2, 0.0)
            if p.subscription.included_in_subscription or p.raw_price == 0.0:
                return (0, p.raw_price)
            return (1, p.raw_price)

        all_products.sort(key=sort_key)

        # Сохраняем в кэш
        if all_products:
            self._set_cached(key, all_products)

        return all_products

    async def _safe_search(
        self, parser: BaseParser, game_name: str, regions: List[str]
    ) -> List[GameProduct]:
        try:
            results = await parser.search(game_name, regions)
            logger.info("[%s] found %d results", parser.store_name, len(results))
            return results
        except Exception:
            logger.warning(
                "[%s] search failed for '%s'", parser.store_name, game_name, exc_info=True
            )
            return []
