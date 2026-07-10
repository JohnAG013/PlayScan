import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Настройки Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

# Валюты, которые поддерживает бот
CURRENCIES = {
    "USD": "$",
    "EUR": "€",
    "RUB": "₽",
    "UAH": "₴",
    "TRY": "₺",
    "KZT": "₸",
    "BRL": "R$",
    "PLN": "zł",
    "GBP": "£",
    "JPY": "¥",
}

# Устройства / платформы
DEVICES = {
    "pc": "PC (Steam, GOG, Epic...)",
    "ps": "PlayStation",
    "xbox": "Xbox",
    "nintendo": "Nintendo Switch",
    "all": "Все платформы",
}

# Кэш пользователей в памяти
_users_cache: dict[int, dict] = {}
_cache_loaded = False
_worksheet = None

# Кэш алертов
_alerts_cache: dict[int, list[dict]] = {}
_alerts_sheet = None
_alerts_loaded = False

# Кэш лимитов поиска (считает за текущий день)
_search_counts: dict[str, int] = {}  # "user_id:YYYY-MM-DD" -> count
DAILY_SEARCH_LIMIT = 5


def _get_worksheet():
    """Получить лист Google Sheets (с кэшированием)."""
    global _worksheet
    if _worksheet is None:
        try:
            creds = Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SPREADSHEET_ID)
            _worksheet = spreadsheet.worksheet("Users")
        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets: {e}")
            raise
    return _worksheet


def _load_cache():
    """Загрузить всех пользователей в кэш из Google Sheets."""
    global _users_cache, _cache_loaded
    if _cache_loaded:
        return

    try:
        ws = _get_worksheet()
        records = ws.get_all_records()

        _users_cache.clear()
        for row in records:
            try:
                user_id = int(row.get("user_id", 0))
                if user_id:
                    _users_cache[user_id] = {
                        "user_id": user_id,
                        "username": row.get("username", ""),
                        "registration_date": row.get("registration_date", ""),
                        "currency": row.get("currency", "USD"),
                        "device": row.get("device", "all"),
                        "region": row.get("region", "global"),
                        "role": row.get("role", "user"),
                    }
            except (ValueError, TypeError):
                continue

        _cache_loaded = True
        logger.info(f"Загружено {len(_users_cache)} пользователей из Google Sheets")
    except Exception as e:
        logger.error(f"Ошибка загрузки кэша: {e}")
        _users_cache.clear()
        _cache_loaded = True


async def init_db():
    """Инициализация: загрузка кэша из Google Sheets."""
    global _cache_loaded
    _cache_loaded = False
    _load_cache()
    logger.info("Google Sheets база данных инициализирована.")


async def user_exists(user_id: int) -> bool:
    _load_cache()
    return user_id in _users_cache


async def add_user(user_id: int, username: str | None) -> bool:
    _load_cache()

    if user_id in _users_cache:
        return True

    try:
        ws = _get_worksheet()
        row_data = [
            user_id,
            username or "",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "USD",
            "all",
            "user",
        ]
        ws.append_row(row_data, value_input_option="RAW")

        _users_cache[user_id] = {
            "user_id": user_id,
            "username": username or "",
            "currency": "USD",
            "device": "all",
            "role": "user",
        }

        logger.info(f"Пользователь {user_id} (@{username}) добавлен в Google Sheets.")
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя {user_id}: {e}")
        return False


async def get_user_profile(user_id: int) -> dict | None:
    _load_cache()
    return _users_cache.get(user_id)


async def set_user_currency(user_id: int, currency: str) -> bool:
    _load_cache()

    if user_id not in _users_cache:
        return False

    try:
        ws = _get_worksheet()
        cell = ws.find(str(user_id), in_column=1)
        if cell:
            ws.update_cell(cell.row, 4, currency)
            _users_cache[user_id]["currency"] = currency
            return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении валюты {user_id}: {e}")
    return False


async def set_user_device(user_id: int, device: str) -> bool:
    _load_cache()

    if user_id not in _users_cache:
        return False

    try:
        ws = _get_worksheet()
        cell = ws.find(str(user_id), in_column=1)
        if cell:
            ws.update_cell(cell.row, 5, device)
            _users_cache[user_id]["device"] = device
            return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении устройства {user_id}: {e}")
    return False


async def set_user_region(user_id: int, region: str) -> bool:
    """Установить регион пользователя."""
    _load_cache()

    if user_id not in _users_cache:
        return False

    try:
        ws = _get_worksheet()
        cell = ws.find(str(user_id), in_column=1)
        if cell:
            ws.update_cell(cell.row, 6, region)
            _users_cache[user_id]["region"] = region
            return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении региона {user_id}: {e}")
    return False


# ─────────────── Лимиты поиска ───────────────

def can_search(user_id: int) -> bool:
    """Проверить, может ли пользователь искать."""
    # Все пользователи могут искать без ограничений
    return True


def increment_search_count(user_id: int) -> int:
    """Увеличить счётчик поиска. Возвращает оставшееся количество."""
    from datetime import date
    today = date.today().isoformat()
    key = f"{user_id}:{today}"
    count = _search_counts.get(key, 0)
    _search_counts[key] = count + 1
    return DAILY_SEARCH_LIMIT - _search_counts[key]


# ─────────────── Алерты (отслеживание цен) ───────────────

def _get_alerts_worksheet():
    """Получить лист алертов."""
    global _alerts_sheet
    if _alerts_sheet is None:
        try:
            creds = Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(SPREADSHEET_ID)

            # Создаём лист Alerts если его нет
            try:
                _alerts_sheet = spreadsheet.worksheet("Alerts")
            except gspread.exceptions.WorksheetNotFound:
                _alerts_sheet = spreadsheet.add_worksheet(title="Alerts", rows=1000, cols=5)
                _alerts_sheet.update("A1:E1", [["user_id", "game_title", "target_price", "currency", "active"]])

        except Exception as e:
            logger.error(f"Ошибка подключения к листу алертов: {e}")
            raise
    return _alerts_sheet


def _load_alerts():
    """Загрузить алерты в кэш."""
    global _alerts_cache, _alerts_loaded
    if _alerts_loaded:
        return

    try:
        ws = _get_alerts_worksheet()
        records = ws.get_all_records()

        _alerts_cache.clear()
        for row in records:
            try:
                user_id = int(row.get("user_id", 0))
                if user_id and str(row.get("active", "")).lower() == "true":
                    if user_id not in _alerts_cache:
                        _alerts_cache[user_id] = []
                    _alerts_cache[user_id].append({
                        "game_title": row.get("game_title", ""),
                        "target_price": float(row.get("target_price", 0)),
                        "currency": row.get("currency", "USD"),
                    })
            except (ValueError, TypeError):
                continue

        _alerts_loaded = True
        logger.info(f"Загружено {sum(len(v) for v in _alerts_cache.values())} алертов")
    except Exception as e:
        logger.error(f"Ошибка загрузки алертов: {e}")
        _alerts_loaded = True


async def add_alert(user_id: int, game_title: str, target_price: float, currency: str = "USD") -> bool:
    """Добавить алерт на цену."""
    _load_alerts()

    try:
        ws = _get_alerts_worksheet()
        ws.append_row([user_id, game_title, target_price, currency, "true"], value_input_option="RAW")

        if user_id not in _alerts_cache:
            _alerts_cache[user_id] = []
        _alerts_cache[user_id].append({
            "game_title": game_title,
            "target_price": target_price,
            "currency": currency,
        })

        logger.info(f"Добавлен алерт: {user_id} -> {game_title} <= {target_price} {currency}")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления алерта: {e}")
        return False


async def get_user_alerts(user_id: int) -> list[dict]:
    """Получить алерты пользователя."""
    _load_alerts()
    return _alerts_cache.get(user_id, [])


async def remove_alert(user_id: int, game_title: str) -> bool:
    """Удалить алерт по названию игры."""
    _load_alerts()

    try:
        ws = _get_alerts_worksheet()
        cell = ws.find(game_title, in_column=2)

        # Ищем алерт именно этого пользователя
        while cell:
            row_data = ws.row_values(cell.row)
            if str(row_data[0]) == str(user_id):
                ws.update_cell(cell.row, 5, "false")
                if user_id in _alerts_cache:
                    _alerts_cache[user_id] = [
                        a for a in _alerts_cache[user_id]
                        if a["game_title"] != game_title
                    ]
                return True
            cell = ws.find(game_title, in_column=2, starting_row=cell.row + 1)

    except Exception as e:
        logger.error(f"Ошибка удаления алерта: {e}")
    return False


async def get_all_active_alerts() -> list[dict]:
    """Получить все активные алерты для проверки цен."""
    _load_alerts()

    all_alerts = []
    for user_id, alerts in _alerts_cache.items():
        for alert in alerts:
            all_alerts.append({
                "user_id": user_id,
                "game_title": alert["game_title"],
                "target_price": alert["target_price"],
                "currency": alert["currency"],
            })

    return all_alerts


async def trigger_alert(user_id: int, game_title: str) -> bool:
    """Отметить алерт как сработавший (деактивировать)."""
    try:
        ws = _get_alerts_worksheet()
        cell = ws.find(game_title, in_column=2)

        while cell:
            row_data = ws.row_values(cell.row)
            if str(row_data[0]) == str(user_id):
                ws.update_cell(cell.row, 5, "false")
                if user_id in _alerts_cache:
                    _alerts_cache[user_id] = [
                        a for a in _alerts_cache[user_id]
                        if a["game_title"] != game_title
                    ]
                return True
            cell = ws.find(game_title, in_column=2, starting_row=cell.row + 1)

    except Exception as e:
        logger.error(f"Ошибка деактивации алерта: {e}")
    return False
