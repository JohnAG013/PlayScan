import re
from difflib import SequenceMatcher
from playfetch.models import GameProduct


def _normalize(text: str) -> str:
    """Нормализует текст для сравнения: убирает точки, двоеточия, спецсимволы."""
    text = text.lower()
    text = re.sub(r"[.\-:;!?\"'()™®©\[\]{}]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fuzzy_filter(
    products: list[GameProduct],
    query: str,
    threshold: float = 0.55,
) -> list[GameProduct]:
    """Фильтрует результаты по схожести с запросом.

    Отсеивает мусорные результаты (кнопки сортировки, левые DLC и т.д.).
    Порог threshold — минимальный % схожести (0.0–1.0).
    """
    normalized_query = _normalize(query)
    filtered = []

    for p in products:
        normalized_title = _normalize(p.title)

        # Прямое сравнение
        ratio = SequenceMatcher(None, normalized_query, normalized_title).ratio()

        # Проверка: запрос является подстрокой названия или наоборот
        if normalized_query in normalized_title or normalized_title in normalized_query:
            ratio = max(ratio, 0.85)

        if ratio >= threshold:
            filtered.append(p)

    return filtered
