import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://open.er-api.com/v6/latest/{base}"


class CurrencyConverter:
    """Конвертер валют. Один раз загружает курсы и кеширует их."""

    def __init__(self):
        self._rates: dict[str, float] = {}
        self._base: str = "USD"

    async def load(self, base: str = "USD") -> None:
        """Загружает курсы валют относительно base."""
        self._base = base.upper()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(_API_URL.format(base=self._base))
                resp.raise_for_status()
                data = resp.json()
                self._rates = data.get("rates", {})
                logger.info("Loaded %d currency rates (base=%s)", len(self._rates), self._base)
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Failed to load currency rates: %s", exc)

    def convert(self, amount: float, from_currency: str, to_currency: str) -> Optional[float]:
        """Конвертирует amount из from_currency в to_currency."""
        if not self._rates:
            return None
        from_cur = from_currency.upper()
        to_cur = to_currency.upper()
        if from_cur == to_cur:
            return amount
        if from_cur not in self._rates or to_cur not in self._rates:
            return None
        # Конвертация через базовую валюту
        in_base = amount / self._rates[from_cur]
        return in_base * self._rates[to_cur]

    def format_conversion(self, amount: float, from_currency: str, to_currency: str) -> Optional[str]:
        """Возвращает строку вида '₺30.09 (~92.40 ₽)' или None."""
        converted = self.convert(amount, from_currency, to_currency)
        if converted is None:
            return None
        # Символы валют
        symbols = {
            "USD": "$", "EUR": "€", "GBP": "£", "RUB": "₽", "TRY": "₺",
            "KZT": "₸", "JPY": "¥", "KRW": "₩", "BRL": "R$", "PLN": "zł",
            "UAH": "₴", "INR": "₹", "ARS": "$", "AUD": "A$", "CAD": "C$",
            "MXN": "M$", "ZAR": "R",
        }
        sym = symbols.get(to_currency.upper(), "")
        return f"~{converted:.2f} {sym}"
