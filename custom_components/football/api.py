from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import BASE_URL


class FootballApiClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _request(self, endpoint: str) -> Any:
        url = f"{BASE_URL}/{endpoint}"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_teams(self, shortcut: str, season: int) -> list[dict[str, Any]]:
        return await self._request(
            f"getavailableteams/{shortcut}/{season}"
        )

    async def get_match_data(
        self, shortcut: str, season: int
    ) -> list[dict[str, Any]]:
        return await self._request(f"getmatchdata/{shortcut}/{season}")

    async def get_current_group(self, shortcut: str) -> dict[str, Any] | None:
        try:
            return await self._request(f"getcurrentgroup/{shortcut}")
        except Exception:
            return None

    async def validate_league(
        self, shortcut: str, season: int
    ) -> bool:
        try:
            data = await self.get_teams(shortcut, season)
            return isinstance(data, list)
        except Exception:
            return False
