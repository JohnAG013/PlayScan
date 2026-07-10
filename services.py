import aiohttp
import logging
import time
import re
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"

# --- Регионы и магазины ---
REGION_MAP = {
    1: {"region": "🌍 Steam", "name": "Steam", "country": "global"},
    7: {"region": "🌍 GOG", "name": "GOG", "country": "global"},
    11: {"region": "🌍 Humble", "name": "Humble Bundle", "country": "global"},
    13: {"region": "🌍 Ubisoft", "name": "Ubisoft Store", "country": "global"},
    15: {"region": "🌍 Fanatical", "name": "Fanatical", "country": "global"},
    21: {"region": "🇺🇸 WinGameStore", "name": "WinGameStore", "country": "usa"},
    23: {"region": "🇩🇪 GameBillet", "name": "GameBillet", "country": "germany"},
    24: {"region": "🌍 Voidu", "name": "Voidu", "country": "global"},
    25: {"region": "🌍 Epic Games", "name": "Epic Games Store", "country": "global"},
    27: {"region": "🇫🇷 Gamesplanet", "name": "Gamesplanet", "country": "france"},
    28: {"region": "🇩🇪 Gamesload", "name": "Gamesload", "country": "germany"},
    29: {"region": "🇬🇧 2Game", "name": "2Game", "country": "uk"},
    30: {"region": "🇮🇹 IndieGala", "name": "IndieGala", "country": "italy"},
    31: {"region": "🇷🇺 Bluesky", "name": "Bluesky", "country": "russia"},
    33: {"region": "🌍 DLGamer", "name": "DLGamer", "country": "global"},
    34: {"region": "🌍 Noctre", "name": "Noctre", "country": "global"},
    35: {"region": "🌍 DreamGame", "name": "DreamGame", "country": "global"},
}

# Все регионы для выбора
ALL_REGIONS = {
    "global": {"name": "🌍 Все регионы", "emoji": "🌍"},
    # Европа
    "ru": {"name": "🇷🇺 Россия", "emoji": "🇷🇺"},
    "uk": {"name": "🇬🇧 Великобритания", "emoji": "🇬🇧"},
    "de": {"name": "🇩🇪 Германия", "emoji": "🇩🇪"},
    "fr": {"name": "🇫🇷 Франция", "emoji": "🇫🇷"},
    "it": {"name": "🇮🇹 Италия", "emoji": "🇮🇹"},
    "es": {"name": "🇪🇸 Испания", "emoji": "🇪🇸"},
    "pt": {"name": "🇵🇹 Португалия", "emoji": "🇵🇹"},
    "nl": {"name": "🇳🇱 Нидерланды", "emoji": "🇳🇱"},
    "pl": {"name": "🇵🇱 Польша", "emoji": "🇵🇱"},
    "cz": {"name": "🇨🇿 Чехия", "emoji": "🇨🇿"},
    "se": {"name": "🇸🇪 Швеция", "emoji": "🇸🇪"},
    "no": {"name": "🇳🇴 Норвегия", "emoji": "🇳🇴"},
    "fi": {"name": "🇫🇮 Финляндия", "emoji": "🇫🇮"},
    "dk": {"name": "🇩🇰 Дания", "emoji": "🇩🇰"},
    "at": {"name": "🇦🇹 Австрия", "emoji": "🇦🇹"},
    "ch": {"name": "🇨🇭 Швейцария", "emoji": "🇨🇭"},
    "be": {"name": "🇧🇪 Бельгия", "emoji": "🇧🇪"},
    "ie": {"name": "🇮🇪 Ирландия", "emoji": "🇮🇪"},
    "ro": {"name": "🇷🇴 Румыния", "emoji": "🇷🇴"},
    "bg": {"name": "🇧🇬 Болгария", "emoji": "🇧🇬"},
    "hr": {"name": "🇭🇷 Хорватия", "emoji": "🇭🇷"},
    "ua": {"name": "🇺🇦 Украина", "emoji": "🇺🇦"},
    "by": {"name": "🇧🇾 Беларусь", "emoji": "🇧🇾"},
    "kz": {"name": "🇰🇿 Казахстан", "emoji": "🇰🇿"},
    # Северная Америка
    "us": {"name": "🇺🇸 США", "emoji": "🇺🇸"},
    "ca": {"name": "🇨🇦 Канада", "emoji": "🇨🇦"},
    "mx": {"name": "🇲🇽 Мексика", "emoji": "🇲🇽"},
    # Южная Америка
    "br": {"name": "🇧🇷 Бразилия", "emoji": "🇧🇷"},
    "ar": {"name": "🇦🇷 Аргентина", "emoji": "🇦🇷"},
    "cl": {"name": "🇨🇱 Чили", "emoji": "🇨🇱"},
    "co": {"name": "🇨🇴 Колумбия", "emoji": "🇨🇴"},
    "pe": {"name": "🇵🇪 Перу", "emoji": "🇵🇪"},
    # Азия
    "cn": {"name": "🇨🇳 Китай", "emoji": "🇨🇳"},
    "jp": {"name": "🇯🇵 Япония", "emoji": "🇯🇵"},
    "kr": {"name": "🇰🇷 Южная Корея", "emoji": "🇰🇷"},
    "in": {"name": "🇮🇳 Индия", "emoji": "🇮🇳"},
    "id": {"name": "🇮🇩 Индонезия", "emoji": "🇮🇩"},
    "th": {"name": "🇹🇭 Таиланд", "emoji": "🇹🇭"},
    "vn": {"name": "🇻🇳 Вьетнам", "emoji": "🇻🇳"},
    "ph": {"name": "🇵🇭 Филиппины", "emoji": "🇵🇭"},
    "my": {"name": "🇲🇾 Малайзия", "emoji": "🇲🇾"},
    "sg": {"name": "🇸🇬 Сингапур", "emoji": "🇸🇬"},
    "tw": {"name": "🇹🇼 Тайвань", "emoji": "🇹🇼"},
    "hk": {"name": "🇭🇰 Гонконг", "emoji": "🇭🇰"},
    "tr": {"name": "🇹🇷 Турция", "emoji": "🇹🇷"},
    "il": {"name": "🇮🇱 Израиль", "emoji": "🇮🇱"},
    "ae": {"name": "🇦🇪 ОАЭ", "emoji": "🇦🇪"},
    "sa": {"name": "🇸🇦 Саудовская Аравия", "emoji": "🇸🇦"},
    # Океания
    "au": {"name": "🇦🇺 Австралия", "emoji": "🇦🇺"},
    "nz": {"name": "🇳🇿 Новая Зеландия", "emoji": "🇳🇿"},
    # Африка
    "za": {"name": "🇿🇦 ЮАР", "emoji": "🇿🇦"},
    "eg": {"name": "🇪🇬 Египет", "emoji": "🇪🇬"},
    "ng": {"name": "🇳🇬 Нигерия", "emoji": "🇳🇬"},
    "ke": {"name": "🇰🇪 Кения", "emoji": "🇰🇪"},
}

# Маппинг для поиска по региону
REGION_ALIASES = {}
for key, info in ALL_REGIONS.items():
    REGION_ALIASES[key] = key
    # Добавляем русские названия
    name_lower = info["name"].lower().split(" ", 1)[-1] if " " in info["name"].lower() else info["name"].lower()
    REGION_ALIASES[name_lower] = key

# Дополнительные алиасы
REGION_ALIASES.update({
    "россия": "ru", "сша": "us", "германия": "de", "франция": "fr",
    "италия": "it", "испания": "es", "великобритания": "uk", "англия": "uk",
    "бразилия": "br", "япония": "jp", "китай": "cn", "корея": "kr",
    "индиа": "in", "индия": "in", "турция": "tr", "австралия": "au",
    "все": "global", "all": "global", "мир": "global",
})

# --- Подписочные сервисы ---
SUBSCRIPTION_SERVICES = {
    "ps_plus": {
        "name": "PS Plus",
        "tiers": ["Essential", "Extra", "Premium"],
        "emoji": "🎮",
    },
    "xbox_game_pass": {
        "name": "Xbox Game Pass",
        "tiers": ["Console", "PC", "Ultimate"],
        "emoji": "🟩",
    },
    "ea_play": {
        "name": "EA Play",
        "tiers": ["Basic", "Pro"],
        "emoji": "🎯",
    },
    "ubisoft_plus": {
        "name": "Ubisoft+",
        "tiers": ["Classic", "Premium"],
        "emoji": "🏰",
    },
}

# Популярные игры в подписках (обновляется вручную)
# Формат: "название_игры": ["сервис1", "сервис2"]
GAMES_IN_SUBSCRIPTIONS = {
    "cyberpunk 2077": ["xbox_game_pass"],
    "the witcher 3": ["xbox_game_pass", "ps_plus"],
    "elden ring": [],
    "fifa 23": ["ea_play"],
    "fifa 24": ["ea_play"],
    "ea fc 24": ["ea_play"],
    "ea fc 25": ["ea_play"],
    "battlefield 2042": ["ea_play"],
    "battlefield v": ["ea_play"],
    "apex legends": [],
    "star wars jedi": ["ea_play"],
    "star wars fallen order": ["ea_play"],
    "star wars survivor": [],
    "need for speed": ["ea_play"],
    "assassin's creed": ["ubisoft_plus", "ps_plus"],
    "far cry": ["ubisoft_plus", "ps_plus"],
    "watch dogs": ["ubisoft_plus", "ps_plus"],
    "rainbow six": ["ubisoft_plus"],
    "forza horizon": ["xbox_game_pass"],
    "forza motorsport": ["xbox_game_pass"],
    "halo infinite": ["xbox_game_pass"],
    "starfield": ["xbox_game_pass"],
    "diablo iv": ["xbox_game_pass"],
    "call of duty": [],
    "grand theft auto": [],
    "red dead redemption": [],
    "horizon zero dawn": ["ps_plus"],
    "horizon forbidden west": ["ps_plus"],
    "god of war": ["ps_plus"],
    "god of war ragnarok": ["ps_plus"],
    "spider-man": ["ps_plus"],
    "spider-man miles morales": ["ps_plus"],
    "the last of us": ["ps_plus"],
    "ghost of tsushima": ["ps_plus"],
    "returnal": ["ps_plus"],
    "ratchet clank": ["ps_plus"],
    "uncharted": ["ps_plus"],
    "gran turismo": ["ps_plus"],
    "days gone": ["ps_plus"],
    "infamous": ["ps_plus"],
    "bloodborne": ["ps_plus"],
    "demon's souls": [],
    "final fantasy": [],
    "resident evil": [],
    "monster hunter": [],
    "dark souls": [],
    "sekiro": [],
    "nioh": ["ps_plus"],
    "Persona 5": ["ps_plus", "xbox_game_pass"],
}

# --- Store cache ---
_store_cache: dict[int, dict] = {}  # storeID -> {name, platform}

# Маппинг магазинов CheapShark на платформы
STORE_PLATFORM_MAP = {
    1: "pc",    # Steam
    7: "pc",    # GOG
    11: "pc",   # Humble Store
    13: "pc",   # Uplay
    15: "pc",   # Fanatical
    21: "pc",   # WinGameStore
    23: "pc",   # GameBillet
    24: "pc",   # Voidu
    25: "pc",   # Epic Games Store
    27: "pc",   # Gamesplanet
    28: "pc",   # Gamesload
    29: "pc",   # 2Game
    30: "pc",   # IndieGala
    31: "pc",   # Bluestacks
    33: "pc",   # DLGamer
    34: "pc",   # Noctre
    35: "pc",   # DreamGame
}

# Консольные магазины (для поиска ссылок)
CONSOLE_STORES = {
    "ps": {
        "name": "PlayStation Store",
        "emoji": "🎮",
        "url_template": "https://store.playstation.com/search/{query}",
    },
    "xbox": {
        "name": "Xbox Store",
        "emoji": "🟩",
        "url_template": "https://www.xbox.com/games/store/search?q={query}",
    },
    "nintendo": {
        "name": "Nintendo eShop",
        "emoji": "🔴",
        "url_template": "https://www.nintendo.com/us/search/#q={query}&p=1&cat=gme",
    },
}


def _build_store_link(store_name: str, steam_app_id: str | None, game_title: str) -> str:
    """Построить прямую ссылку на магазин."""
    store_lower = store_name.lower()

    # Steam
    if "steam" in store_lower and steam_app_id:
        return f"https://store.steampowered.com/app/{steam_app_id}/"

    # GOG
    if "gog" in store_lower:
        return f"https://www.gog.com/games?query={quote_plus(game_title)}"

    # Epic Games
    if "epic" in store_lower:
        return f"https://store.epicgames.com/en-US/browse?q={quote_plus(game_title)}&sortBy=relevancy&sortDir=DESC&count=40"

    # Humble Bundle
    if "humble" in store_lower:
        return f"https://www.humblebundle.com/store/search?search={quote_plus(game_title)}"

    # Fanatical
    if "fanatical" in store_lower:
        return f"https://www.fanatical.com/en/search?search={quote_plus(game_title)}"

    # Ubisoft
    if "ubisoft" in store_lower:
        return f"https://store.ubi.com/search?query={quote_plus(game_title)}"

    # Fallback — поиск в Google
    return f"https://www.google.com/search?q={quote_plus(game_title + ' buy ' + store_name)}"

# --- Exchange rate cache ---
_rate_cache: dict[str, float] = {}
_rate_cache_time: float = 0
_RATE_CACHE_TTL = 3600  # 1 час


async def _fetch_stores(session: aiohttp.ClientSession) -> dict[int, dict]:
    """Получить и закешировать список магазинов CheapShark с маппингом платформ."""
    global _store_cache
    if _store_cache:
        return _store_cache

    try:
        async with session.get(
            f"{CHEAPSHARK_BASE}/stores", timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status == 200:
                stores = await resp.json()
                for s in stores:
                    sid = str(s["storeID"])
                    _store_cache[sid] = {
                        "name": s["storeName"],
                        "platform": STORE_PLATFORM_MAP.get(int(sid), "pc"),
                    }
                return _store_cache
    except Exception as e:
        logger.warning(f"Не удалось загрузить список магазинов: {e}")

    return {}


async def _get_exchange_rates(session: aiohttp.ClientSession) -> dict[str, float]:
    """Получить курсы валют (USD -> X). Кеш на 1 час."""
    global _rate_cache, _rate_cache_time

    now = time.time()
    if _rate_cache and (now - _rate_cache_time) < _RATE_CACHE_TTL:
        return _rate_cache

    try:
        async with session.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                _rate_cache = data.get("rates", {})
                _rate_cache_time = now
                return _rate_cache
    except Exception as e:
        logger.warning(f"Не удалось загрузить курсы валют: {e}")

    return _rate_cache or {"USD": 1}


def convert_price(usd_price: float, to_currency: str, rates: dict[str, float]) -> float | None:
    """Конвертировать цену из USD в целевую валюту."""
    if to_currency == "USD":
        return usd_price
    rate = rates.get(to_currency)
    if rate:
        return round(usd_price * rate, 2)
    return None


async def search_games(query: str, limit: int = 5) -> list[dict]:
    """Поиск игр через CheapShark API."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/games",
                params={"title": query, "limit": limit, "exact": 0},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                games = await resp.json()
                return [
                    {
                        "game_id": g.get("gameID"),
                        "title": g.get("external", "Без названия"),
                        "cheapest": g.get("cheapest", "?"),
                        "cheapest_store": g.get("cheapestStoreID"),
                    }
                    for g in games
                ]
        except Exception as e:
            logger.error(f"Ошибка при поиске игр: {e}")
            return []


async def get_game_deals(
    game_id: str,
    target_currency: str = "USD",
    target_platform: str = "all",
) -> list[dict]:
    """Получить цены на игру во всех магазинах с конвертацией и фильтром платформы."""
    async with aiohttp.ClientSession() as session:
        stores = await _fetch_stores(session)
        rates = await _get_exchange_rates(session)

        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/games",
                params={"id": game_id, "limit": 50},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                deals = data.get("deals", [])
                info = data.get("info", {})
                steam_app_id = info.get("steamAppID")
                game_title = info.get("title", "Без названия")

                results = []
                for deal in deals:
                    store_id = str(deal.get("storeID", "0"))
                    store_info = stores.get(store_id, {"name": f"Store #{store_id}", "platform": "pc"})
                    store_platform = store_info["platform"]

                    if target_platform != "all" and store_platform != target_platform:
                        continue

                    usd_price = float(deal.get("price", 0))
                    converted = convert_price(usd_price, target_currency, rates)

                    # Прямая ссылка: Steam через steamAppID, остальные — CheapShark redirect
                    if store_id == "1" and steam_app_id:
                        link = f"https://store.steampowered.com/app/{steam_app_id}/"
                    elif steam_app_id:
                        # Ищем магазин в STORE_PLATFORM_MAP чтобы построить ссылку
                        store_name = stores.get(store_id, {}).get("name", "")
                        link = _build_store_link(store_name, steam_app_id, game_title)
                    else:
                        link = f"https://www.cheapshark.com/redirect?dealID={deal.get('dealID', '')}"

                    # Ссылка на страницу игры
                    if steam_app_id:
                        game_link = f"https://store.steampowered.com/app/{steam_app_id}/"
                    else:
                        game_link = _build_store_link(stores.get(store_id, {}).get("name", ""), None, game_title)

                    results.append({
                        "title": game_title,
                        "price_usd": f"{usd_price:.2f}",
                        "price_converted": f"{converted:.2f}" if converted else None,
                        "currency": target_currency,
                        "normal_price": deal.get("retailPrice", "?"),
                        "savings": round(float(deal.get("savings", 0)), 1),
                        "store": store_info["name"],
                        "platform": store_platform,
                        "link": link,
                        "game_link": game_link,
                        "metacritic": deal.get("metacriticScore"),
                    })

                results.sort(key=lambda x: float(x["price_usd"]) if x["price_usd"] not in ("?", "", None) else 9999)
                return results

        except Exception as e:
            logger.error(f"Ошибка при получении сделок: {e}")
            return []


async def _batch_get_steam_ids(
    session: aiohttp.ClientSession, titles: list[str]
) -> dict[str, str]:
    """Получить steamAppID для списка уникальных названий игр."""
    result = {}
    seen = set()
    for title in titles:
        t = title.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/games",
                params={"title": t, "limit": 1, "exact": 0},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    games = await resp.json()
                    if games:
                        game_id = games[0].get("gameID")
                        if game_id:
                            async with session.get(
                                f"{CHEAPSHARK_BASE}/games",
                                params={"id": game_id},
                                timeout=aiohttp.ClientTimeout(total=8),
                            ) as resp2:
                                if resp2.status == 200:
                                    detail = await resp2.json()
                                    sid = detail.get("info", {}).get("steamAppID")
                                    if sid:
                                        result[t.lower()] = str(sid)
        except Exception:
            pass
    return result


async def search_deals(
    query: str,
    limit: int = 10,
    target_currency: str = "USD",
    target_platform: str = "all",
) -> list[dict]:
    """Прямой поиск сделок с конвертацией и фильтром платформы."""
    async with aiohttp.ClientSession() as session:
        stores = await _fetch_stores(session)
        rates = await _get_exchange_rates(session)

        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/deals",
                params={"title": query, "limit": 100, "sortBy": "Deal Rating", "desc": 0},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []

                deals = await resp.json()

                # Собираем уникальные названия для пакетного поиска steamAppID
                unique_titles = list({d.get("title", "") for d in deals if d.get("title")})
                steam_ids = await _batch_get_steam_ids(session, unique_titles)

                results = []
                for deal in deals:
                    store_id = str(deal.get("storeID", "0"))
                    store_info = stores.get(store_id, {"name": f"Store #{store_id}", "platform": "pc"})
                    store_platform = store_info["platform"]

                    if target_platform != "all" and store_platform != target_platform:
                        continue

                    usd_price = float(deal.get("salePrice", 0))
                    converted = convert_price(usd_price, target_currency, rates)

                    game_title = deal.get("title", "Без названия")
                    steam_id = steam_ids.get(game_title.lower())

                    # Прямая Steam-ссылка или ссылка на магазин
                    if store_id == "1" and steam_id:
                        link = f"https://store.steampowered.com/app/{steam_id}/"
                    elif steam_id:
                        link = _build_store_link(store_info["name"], steam_id, game_title)
                    else:
                        link = f"https://www.cheapshark.com/redirect?dealID={deal.get('dealID', '')}"

                    # Ссылка на страницу игры
                    if steam_id:
                        game_link = f"https://store.steampowered.com/app/{steam_id}/"
                    else:
                        game_link = _build_store_link(store_info["name"], None, game_title)

                    results.append({
                        "title": game_title,
                        "price_usd": f"{usd_price:.2f}",
                        "price_converted": f"{converted:.2f}" if converted else None,
                        "currency": target_currency,
                        "normal_price": deal.get("normalPrice", "?"),
                        "savings": round(float(deal.get("savings", 0)), 1),
                        "store": store_info["name"],
                        "platform": store_platform,
                        "link": link,
                        "game_link": game_link,
                        "metacritic": deal.get("metacriticScore"),
                        "steam_rating": deal.get("steamRatingPercent"),
                    })

                    if len(results) >= limit:
                        break

                return results

        except Exception as e:
            logger.error(f"Ошибка при поиске сделок: {e}")
            return []


async def get_stores_list() -> list[dict]:
    """Получить список магазинов с платформами."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/stores", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                stores = await resp.json()
                return [
                    {
                        "id": s.get("storeID"),
                        "name": s.get("storeName"),
                        "active": s.get("isActive"),
                        "platform": STORE_PLATFORM_MAP.get(s.get("storeID"), "pc"),
                    }
                    for s in stores
                ]
        except Exception as e:
            logger.error(f"Ошибка при загрузке списка магазинов: {e}")
            return []


# --- Официальные магазины для поиска ---
OFFICIAL_STORES = [
    "store.steampowered.com",
    "store.epicgames.com",
    "gog.com",
    "play.google.com",
    "apps.apple.com",
    "nintendo.com",
    "playstation.com",
    "xbox.com",
    "ubisoft.com",
    "ea.com",
    "battle.net",
    "store.ubi.com",
    "rockstargames.com",
    "blizzard.com",
    "riotgames.com",
]


async def search_game_official_link(
    session: aiohttp.ClientSession, game_title: str
) -> tuple[str, str | None]:
    """Ищет официальную ссылку на игру через DuckDuckGo. Возвращает (title, link)."""
    query = f"{game_title} game buy official store"
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=5),
            headers={"User-Agent": "Mozilla/5.0"},
        ) as resp:
            if resp.status != 200:
                return game_title, None
            html = await resp.text()

            # Ищем ссылки в результатах
            links = re.findall(r'href="(https?://[^"]+)"', html)

            # Фильтруем только официальные магазины
            for link in links:
                for store in OFFICIAL_STORES:
                    if store in link and "duckduckgo" not in link:
                        clean_link = link.split("?")[0]
                        if clean_link.endswith("/"):
                            clean_link = clean_link[:-1]
                        return game_title, clean_link

            # Если не нашли официальный магазин, ищем любую подходящую ссылку
            for link in links:
                if "duckduckgo" not in link and "google" not in link and "youtube" not in link:
                    return game_title, link.split("?")[0]

    except Exception as e:
        logger.warning(f"Ошибка при поиске официальной ссылки для {game_title}: {e}")

    return game_title, None


async def enrich_deals_with_official_links(deals: list[dict]) -> list[dict]:
    """Обогащает список сделок официальными ссылками на игры (параллельно)."""
    import asyncio

    unique_titles = list({deal["title"] for deal in deals})[:3]

    try:
        async with aiohttp.ClientSession() as session:
            tasks = [
                search_game_official_link(session, title)
                for title in unique_titles
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            official_links = {}
            for result in results:
                if isinstance(result, tuple):
                    title, link = result
                    if link:
                        official_links[title] = link

            for deal in deals:
                if deal["title"] in official_links:
                    deal["official_link"] = official_links[deal["title"]]

    except Exception as e:
        logger.warning(f"Ошибка при обогащении ссылками: {e}")

    return deals


# ─────────────── Подписки ───────────────

async def search_subscription_online(game_title: str) -> dict:
    """Искать информацию о подписках через DuckDuckGo."""
    import asyncio

    result = {
        "game_title": game_title,
        "subscriptions": [],
        "source": "web"
    }

    # Ключевые слова для поиска подписок
    subscription_keywords = {
        "ps plus": "🎮 PS Plus",
        "playstation plus": "🎮 PS Plus",
        "ps now": "🎮 PS Plus",
        "xbox game pass": "🟩 Xbox Game Pass",
        "game pass": "🟩 Xbox Game Pass",
        "ea play": "🎯 EA Play",
        "ea access": "🎯 EA Play",
        "ubisoft+": "🏰 Ubisoft+",
        "ubisoft plus": "🏰 Ubisoft+",
        "apple arcade": "🍎 Apple Arcade",
        "humble choice": "🎁 Humble Choice",
    }

    search_queries = [
        f"{game_title} ps plus subscription",
        f"{game_title} xbox game pass",
        f"{game_title} ea play",
        f"{game_title} subscription available",
    ]

    try:
        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                try:
                    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=8),
                        headers={"User-Agent": "Mozilla/5.0"},
                    ) as resp:
                        if resp.status != 200:
                            continue

                        html = await resp.text()
                        text_lower = html.lower()

                        for keyword, service_name in subscription_keywords.items():
                            if keyword in text_lower:
                                # Проверяем, что сервис ещё не добавлен
                                if not any(s["service"] == service_name for s in result["subscriptions"]):
                                    result["subscriptions"].append({
                                        "service": service_name,
                                        "found_in": query,
                                    })

                except Exception as e:
                    logger.warning(f"Ошибка поиска подписок: {e}")
                    continue

                # Небольшая пауза между запросами
                await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"Ошибка при поиске подписок: {e}")

    return result


def check_subscription_local(game_title: str) -> list[dict]:
    """Проверить локальную базу подписок (fallback)."""
    title_lower = game_title.lower()
    results = []

    for service_key, games_list in GAMES_IN_SUBSCRIPTIONS.items():
        for game_pattern in games_list:
            if game_pattern in title_lower or title_lower in game_pattern:
                service = SUBSCRIPTION_SERVICES.get(service_key, {})
                results.append({
                    "service": service.get("name", service_key),
                    "emoji": service.get("emoji", "🎮"),
                    "tiers": service.get("tiers", []),
                })
                break

    return results


async def check_subscription(game_title: str) -> dict:
    """Проверить подписки: сначала онлайн, потом локальная база."""
    # Пробуем онлайн-поиск
    online_result = await search_subscription_online(game_title)

    if online_result["subscriptions"]:
        return {
            "found_online": True,
            "subscriptions": online_result["subscriptions"],
        }

    # Фоллбэк на локальную базу
    local_result = check_subscription_local(game_title)
    return {
        "found_online": False,
        "subscriptions": local_result,
    }


# ─────────────── Региональные цены ───────────────

async def get_regional_prices(game_title: str, target_currency: str = "USD", filter_region: str = None) -> list[dict]:
    """Получить цены на игру из разных регионов/магазинов."""
    async with aiohttp.ClientSession() as session:
        stores = await _fetch_stores(session)
        rates = await _get_exchange_rates(session)

        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/deals",
                params={"title": game_title, "limit": 100, "sortBy": "Price", "desc": 0},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []

                deals = await resp.json()

                # Группируем по регионам
                regional_deals = {}
                for deal in deals:
                    store_id = int(deal.get("storeID", 0))
                    store_info = REGION_MAP.get(store_id, {"region": "🌍 Steam", "name": "Steam", "country": "global"})

                    region = store_info["region"]
                    country = store_info.get("country", "global")

                    # Фильтр по региону если указан
                    if filter_region and filter_region != "global":
                        if country != filter_region and country != "global":
                            continue

                    if region not in regional_deals:
                        regional_deals[region] = []

                    usd_price = float(deal.get("salePrice", 0))
                    converted = convert_price(usd_price, target_currency, rates)

                    regional_deals[region].append({
                        "store": store_info["name"],
                        "price_usd": usd_price,
                        "price_converted": converted,
                        "savings": round(float(deal.get("savings", 0)), 1),
                        "link": f"https://www.cheapshark.com/redirect?dealID={deal.get('dealID', '')}",
                    })

                # Сортируем регионы по минимальной цене
                result = []
                for region, deals_list in sorted(
                    regional_deals.items(),
                    key=lambda x: min(d["price_usd"] for d in x[1])
                ):
                    # Берём лучшую цену в регионе
                    best_deal = min(deals_list, key=lambda x: x["price_usd"])
                    result.append({
                        "region": region,
                        "best_price_usd": best_deal["price_usd"],
                        "best_price_converted": best_deal["price_converted"],
                        "store": best_deal["store"],
                        "savings": best_deal["savings"],
                        "total_deals": len(deals_list),
                        "link": best_deal["link"],
                    })

                return result

        except Exception as e:
            logger.error(f"Ошибка при получении региональных цен: {e}")
            return []


# ─────────────── Проверка цен для алертов ───────────────

async def get_best_price(game_title: str) -> dict | None:
    """Получить лучшую цену на игру. Возвращает {price_usd, store, link} или None."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/deals",
                params={"title": game_title, "limit": 50, "sortBy": "Price", "desc": 0},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None

                deals = await resp.json()

                if not deals:
                    return None

                # Находим лучшую цену
                best_deal = min(deals, key=lambda x: float(x.get("salePrice", 9999)))

                return {
                    "title": best_deal.get("title", game_title),
                    "price_usd": float(best_deal.get("salePrice", 0)),
                    "store": best_deal.get("storeID", ""),
                    "link": f"https://www.cheapshark.com/redirect?dealID={best_deal.get('dealID', '')}",
                    "savings": round(float(best_deal.get("savings", 0)), 1),
                }

        except Exception as e:
            logger.error(f"Ошибка при проверке цены для алерта: {e}")
            return None


# ─────────────── Консольные магазины ───────────────

async def search_console_game(game_title: str, platform: str) -> list[dict]:
    """Поиск игры в консольном магазине."""
    if platform not in CONSOLE_STORES:
        return []

    store_info = CONSOLE_STORES[platform]
    store_name = store_info["name"]
    store_emoji = store_info["emoji"]

    try:
        # Формируем ссылку на поиск
        search_url = store_info["url_template"].format(query=quote_plus(game_title))

        # Возвращаем ссылку на магазин
        return [{
            "title": game_title,
            "store": f"{store_emoji} {store_name}",
            "platform": platform,
            "link": search_url,
            "note": "Перейди по ссылке чтобы увидеть цену",
        }]

    except Exception as e:
        logger.error(f"Ошибка поиска в {store_name}: {e}")
        return []


async def search_all_platforms(game_title: str, target_platform: str = "all", target_currency: str = "USD") -> list[dict]:
    """Поиск игры на всех платформах."""
    results = []

    # PC через CheapShark
    if target_platform in ("all", "pc"):
        pc_deals = await search_deals(game_title, limit=20, target_currency=target_currency, target_platform="pc")
        results.extend(pc_deals)

    # Консоли
    console_platforms = ["ps", "xbox", "nintendo"]
    if target_platform in ("all",) + tuple(console_platforms):
        for platform in console_platforms:
            if target_platform in ("all", platform):
                console_results = await search_console_game(game_title, platform)
                results.extend(console_results)

    return results


# ─────────────── Все сделки для региона ───────────────

async def get_regional_deals(game_title: str, target_currency: str = "USD", filter_region: str = "global") -> list[dict]:
    """Получить ВСЕ сделки для конкретного региона с ссылками."""
    async with aiohttp.ClientSession() as session:
        stores = await _fetch_stores(session)
        rates = await _get_exchange_rates(session)

        try:
            async with session.get(
                f"{CHEAPSHARK_BASE}/deals",
                params={"title": game_title, "limit": 100, "sortBy": "Price", "desc": 0},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []

                deals = await resp.json()

                # Фильтруем по региону и собираем все сделки
                result = []
                for deal in deals:
                    store_id = int(deal.get("storeID", 0))
                    store_info = REGION_MAP.get(store_id, {"region": "🌍 Steam", "name": "Steam", "country": "global"})

                    country = store_info.get("country", "global")

                    # Фильтр по региону
                    if filter_region != "global":
                        if country != filter_region and country != "global":
                            continue

                    usd_price = float(deal.get("salePrice", 0))
                    converted = convert_price(usd_price, target_currency, rates)

                    result.append({
                        "title": deal.get("title", game_title),
                        "store": store_info["name"],
                        "region": store_info["region"],
                        "price_usd": usd_price,
                        "price_converted": converted,
                        "savings": round(float(deal.get("savings", 0)), 1),
                        "link": f"https://www.cheapshark.com/redirect?dealID={deal.get('dealID', '')}",
                        "normal_price": deal.get("normalPrice", "?"),
                    })

                # Сортируем по цене
                result.sort(key=lambda x: x.get("price_converted") or x.get("price_usd", 9999))

                return result

        except Exception as e:
            logger.error(f"Ошибка при получении сделок для региона: {e}")
            return []
