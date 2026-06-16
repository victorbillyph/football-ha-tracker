from __future__ import annotations

from typing import Any

import aiohttp

from .const import BASE_URL


class FootballApiClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _request(self, params: dict[str, str]) -> Any:
        async with self._session.get(BASE_URL, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_teams(self, shortcut: str) -> list[dict[str, Any]]:
        data = await self._request({
            "data": "results",
            "category": "tables",
            "league": shortcut,
        })
        teams: list[dict[str, Any]] = []
        for standing in data.get("data", {}).get("standings", []):
            for entry in standing.get("table", []):
                team = entry["team"]
                teams.append({
                    "teamId": team["id"],
                    "teamName": team["name"],
                })
        return teams

    async def get_match_data(self, shortcut: str) -> list[dict[str, Any]]:
        data = await self._request({
            "data": "results",
            "category": "scores",
            "league": shortcut,
        })
        matches: list[dict[str, Any]] = []
        for status in ("live", "scheduled", "finished"):
            matches.extend(data.get("data", {}).get(status, []))
        return matches
