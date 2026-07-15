from abc import ABC, abstractmethod
from typing import List

from playfetch.models import GameProduct


class BaseParser(ABC):
    store_name: str = "Unknown"

    @abstractmethod
    async def search(self, game_name: str, regions: List[str]) -> List[GameProduct]:
        ...
