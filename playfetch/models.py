from pydantic import BaseModel, Field
from typing import List, Optional


REGION_CURRENCY: dict[str, tuple[str, str]] = {
    "US": ("USD", "$"),
    "GB": ("GBP", "\u00a3"),
    "EU": ("EUR", "\u20ac"),
    "DE": ("EUR", "\u20ac"),
    "FR": ("EUR", "\u20ac"),
    "IT": ("EUR", "\u20ac"),
    "ES": ("EUR", "\u20ac"),
    "NL": ("EUR", "\u20ac"),
    "PT": ("EUR", "\u20ac"),
    "BE": ("EUR", "\u20ac"),
    "AT": ("EUR", "\u20ac"),
    "IE": ("EUR", "\u20ac"),
    "FI": ("EUR", "\u20ac"),
    "RU": ("RUB", "\u20bd"),
    "TR": ("TRY", "\u20ba"),
    "KZ": ("KZT", "\u20b8"),
    "UA": ("UAH", "\u20b4"),
    "PL": ("PLN", "z\u0142"),
    "CZ": ("CZK", "K\u010d"),
    "HU": ("HUF", "Ft"),
    "RO": ("RON", "lei"),
    "BG": ("BGN", "\u043b\u0432"),
    "SE": ("SEK", "kr"),
    "NO": ("NOK", "kr"),
    "DK": ("DKK", "kr"),
    "CH": ("CHF", "CHF"),
    "JP": ("JPY", "\u00a5"),
    "KR": ("KRW", "\u20a9"),
    "CN": ("CNY", "\u00a5"),
    "TW": ("TWD", "NT$"),
    "BR": ("BRL", "R$"),
    "MX": ("MXN", "M$"),
    "AR": ("ARS", "$"),
    "CL": ("CLP", "$"),
    "CO": ("COP", "$"),
    "AU": ("AUD", "A$"),
    "NZ": ("NZD", "NZ$"),
    "CA": ("CAD", "C$"),
    "IN": ("INR", "\u20b9"),
    "ZA": ("ZAR", "R"),
    "SA": ("SAR", "﷼"),
    "AE": ("AED", "AED"),
    "IL": ("ILS", "\u20aa"),
    "TH": ("THB", "\u0e3f"),
    "VN": ("VND", "\u20ab"),
    "ID": ("IDR", "Rp"),
    "MY": ("MYR", "RM"),
    "PH": ("PHP", "\u20b1"),
    "SG": ("SGD", "S$"),
    "HK": ("HKD", "HK$"),
}


class SubscriptionInfo(BaseModel):
    included_in_subscription: bool = Field(default=False)
    subscription_name: Optional[str] = Field(default=None)


class GameProduct(BaseModel):
    title: str
    store_name: str
    platform: str
    region: str
    price: str
    raw_price: Optional[float] = None
    currency: str
    url: str
    subscription: SubscriptionInfo = Field(default_factory=SubscriptionInfo)


def resolve_currency(region: str) -> tuple[str, str]:
    return REGION_CURRENCY.get(region.upper(), ("USD", "$"))
