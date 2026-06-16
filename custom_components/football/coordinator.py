from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import FootballApiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, LIVE_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

STATUS_MAP = {
    "IN_PLAY": "LIVE",
    "PAUSED": "LIVE",
    "FINISHED": "FT",
    "SCHEDULED": "NS",
    "TIMED": "NS",
    "POSTPONED": "NS",
    "CANCELLED": "FT",
    "SUSPENDED": "LIVE",
}


def _format_group(group: str | None) -> str:
    if not group:
        return ""
    g = group.replace("GROUP_", "Group ").replace("_", " ")
    return g.title().strip()


def _format_stage(stage: str | None) -> str:
    if not stage:
        return ""
    s = stage.replace("_", " ").title()
    return s


class FootballDataUpdateCoordinator(
    DataUpdateCoordinator[dict[str, dict[str, Any] | None]]
):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.api = FootballApiClient(async_get_clientsession(hass))

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any] | None]:
        entries = self.entry.data.get("entries", [])
        results: dict[str, dict[str, Any] | None] = {}
        any_live = False

        for entry_conf in entries:
            shortcut = entry_conf["league_shortcut"]
            league_name = entry_conf.get("league_name", shortcut)

            try:
                matches = await self.api.get_match_data(shortcut)
            except Exception as err:
                _LOGGER.error("Error fetching %s: %s", shortcut, err)
                for team in entry_conf.get("teams", []):
                    key = f"{shortcut}_{team['team_id']}"
                    results[key] = {"error": str(err)}
                continue

            for team in entry_conf.get("teams", []):
                key = f"{shortcut}_{team['team_id']}"
                data = self._process_team_matches(
                    matches, team["team_id"], team["team_name"], league_name
                )
                results[key] = data
                if data and data.get("is_live"):
                    any_live = True

        self.update_interval = timedelta(
            seconds=LIVE_SCAN_INTERVAL if any_live else DEFAULT_SCAN_INTERVAL
        )

        return results

    def _process_team_matches(
        self,
        matches: list[dict[str, Any]],
        team_id: int,
        team_name: str,
        league_name: str,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        relevant = []

        for match in matches:
            ht = match.get("homeTeam", {})
            at = match.get("awayTeam", {})
            if ht.get("id") != team_id and at.get("id") != team_id:
                continue
            relevant.append(match)

        if not relevant:
            return None

        live = None
        upcoming = None
        latest = None

        for match in relevant:
            status = match.get("status", "")
            match_time = match.get("utcDate")

            if status in ("IN_PLAY", "PAUSED", "SUSPENDED"):
                live = match
            elif status in ("SCHEDULED", "TIMED", "POSTPONED"):
                if not match_time:
                    continue
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
                if upcoming is None or dt < datetime.fromisoformat(
                    upcoming["utcDate"].replace("Z", "+00:00")
                ):
                    upcoming = match
            elif status in ("FINISHED", "CANCELLED"):
                if not match_time:
                    continue
                try:
                    dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
                if latest is None or (
                    latest.get("utcDate")
                    and dt > datetime.fromisoformat(
                        latest["utcDate"].replace("Z", "+00:00")
                    )
                ):
                    latest = match

        match = live or upcoming or latest
        if not match:
            return None

        return self._extract_data(match, team_id, team_name, league_name)

    @staticmethod
    def _extract_data(
        match: dict[str, Any],
        team_id: int,
        team_name: str,
        league_name: str,
    ) -> dict[str, Any]:
        ht = match.get("homeTeam", {})
        at = match.get("awayTeam", {})

        is_home = ht.get("id") == team_id
        our = ht if is_home else at
        opponent = at if is_home else ht

        raw_status = match.get("status", "")
        status = STATUS_MAP.get(raw_status, "NS")
        is_live = status == "LIVE"

        score = match.get("score", {})
        full_time = score.get("fullTime", {}) or {}
        if is_home:
            our_score = full_time.get("home")
            opp_score = full_time.get("away")
        else:
            our_score = full_time.get("away")
            opp_score = full_time.get("home")

        group = match.get("group", "")
        stage = match.get("stage", "")
        round_name = _format_group(group)
        if stage and not group:
            round_name = _format_stage(stage)

        return {
            "fixture_id": match.get("id"),
            "timestamp": match.get("utcDate"),
            "date": match.get("utcDate"),
            "status": status,
            "team_name": our.get("name", team_name),
            "opponent_name": opponent.get("name", ""),
            "our_score": our_score,
            "opponent_score": opp_score,
            "minute": None,
            "round": round_name,
            "league": league_name,
            "is_live": is_live,
        }
