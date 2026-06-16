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


def _get_match_status(match: dict[str, Any]) -> str:
    if match.get("matchIsFinished"):
        return "FT"
    match_time = match.get("matchDateTimeUTC")
    if not match_time:
        return "NS"
    try:
        dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "NS"
    now = datetime.now(timezone.utc)
    if dt > now:
        return "NS"
    goals = match.get("goals", [])
    if goals:
        return "LIVE"
    return "NS"


def _get_match_minute(match: dict[str, Any]) -> int | None:
    goals = match.get("goals", [])
    if not goals:
        return None
    last_goal = goals[-1]
    minute = last_goal.get("matchMinute", 0)
    overtime = last_goal.get("isOvertime", False)
    comment = last_goal.get("comment", "")
    if overtime:
        return minute if not comment else None
    return minute


def _get_final_score(match: dict[str, Any]) -> tuple[int | None, int | None]:
    results = match.get("matchResults", [])
    for r in results:
        if r.get("resultTypeID") == 2:
            return r.get("pointsTeam1"), r.get("pointsTeam2")
    if results:
        return results[0].get("pointsTeam1"), results[0].get("pointsTeam2")
    return None, None


def _get_live_score(match: dict[str, Any]) -> tuple[int | None, int | None]:
    goals = match.get("goals", [])
    if not goals:
        return None, None
    og = goals[-1]
    return og.get("scoreTeam1"), og.get("scoreTeam2")


class FootballDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any] | None]]):
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
            season = entry_conf["league_season"]
            league_name = entry_conf.get("league_name", f"{shortcut} {season}")

            try:
                matches = await self.api.get_match_data(shortcut, season)
            except Exception as err:
                _LOGGER.error("Error fetching %s/%s: %s", shortcut, season, err)
                for team in entry_conf.get("teams", []):
                    key = f"{shortcut}_{season}_{team['team_id']}"
                    results[key] = {"error": str(err)}
                continue

            for team in entry_conf.get("teams", []):
                key = f"{shortcut}_{season}_{team['team_id']}"
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
            t1 = match.get("team1", {})
            t2 = match.get("team2", {})
            if t1.get("teamId") != team_id and t2.get("teamId") != team_id:
                continue
            relevant.append(match)

        if not relevant:
            return None

        live = None
        upcoming = None
        latest = None

        for match in relevant:
            status = _get_match_status(match)
            match_time = match.get("matchDateTimeUTC")
            try:
                dt = datetime.fromisoformat(match_time.replace("Z", "+00:00"))
            except (ValueError, AttributeError, KeyError):
                dt = None

            if status == "LIVE":
                live = match
            elif status == "NS" and dt:
                if upcoming is None or dt < datetime.fromisoformat(
                    upcoming["matchDateTimeUTC"].replace("Z", "+00:00")
                ):
                    upcoming = match
            elif status == "FT":
                if latest is None or (dt and latest.get("matchDateTimeUTC")
                    and dt > datetime.fromisoformat(
                        latest["matchDateTimeUTC"].replace("Z", "+00:00")
                    )):
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
        is_home = match["team1"]["teamId"] == team_id
        our = match["team1"] if is_home else match["team2"]
        opponent = match["team2"] if is_home else match["team1"]
        status = _get_match_status(match)
        is_live = status == "LIVE"

        if is_live:
            our_score, opp_score = _get_live_score(match)
        else:
            our_score, opp_score = _get_final_score(match)

        minute = _get_match_minute(match)
        group = match.get("group", {})
        round_name = group.get("groupName", "") if group else ""

        return {
            "fixture_id": match.get("matchID"),
            "timestamp": match.get("matchDateTimeUTC"),
            "date": match.get("matchDateTime"),
            "status": status,
            "team_name": our.get("teamName", team_name),
            "opponent_name": opponent.get("teamName", ""),
            "our_score": our_score,
            "opponent_score": opp_score,
            "minute": minute,
            "round": round_name,
            "league": league_name,
            "is_live": is_live,
        }
