from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FootballApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

POPULAR_LEAGUES = {
    "wm26": "World Cup 2026",
    "em": "UEFA EURO 2024",
    "CA2024": "Copa América 2024",
    "unl2024": "Nations League 2024/25",
    "bl1": "Bundesliga",
    "epl": "Premier League",
    "laliga1": "LaLiga",
    "cl1": "Champions League",
}

SEASONS = ["2024", "2025", "2026"]


def _entry_label(entry: dict) -> str:
    league = entry.get("league_name") or entry.get("league_shortcut", "?")
    teams = ", ".join(t["team_name"] for t in entry.get("teams", []))
    return f"{league}: {teams}"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            if user_input["mode"] == "popular":
                return await self.async_step_popular_league()
            return await self.async_step_custom_league()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("mode"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "popular", "label": "Popular competition"},
                            {"value": "custom", "label": "Custom league"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }),
        )

    async def async_step_popular_league(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._league_shortcut = user_input["shortcut"]
            self._league_season = int(user_input["season"])
            self._league_name = POPULAR_LEAGUES.get(
                self._league_shortcut, self._league_shortcut
            )
            return await self._show_team_selection()

        return self.async_show_form(
            step_id="popular_league",
            data_schema=vol.Schema({
                vol.Required("shortcut"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v}
                            for k, v in POPULAR_LEAGUES.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("season"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": s, "label": s} for s in SEASONS
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )

    async def async_step_custom_league(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            shortcut = user_input["shortcut"].strip()
            season = int(user_input["season"])
            session = async_get_clientsession(self.hass)
            client = FootballApiClient(session)
            try:
                teams = await client.get_teams(shortcut, season)
                if isinstance(teams, list) and len(teams) > 0:
                    self._league_shortcut = shortcut
                    self._league_season = season
                    self._league_name = shortcut
                    self._cached_teams = teams
                    return await self._finish_team_selection()
                errors["base"] = "league_not_found"
            except Exception as ex:
                _LOGGER.error("Error validating league %s/%s: %s", shortcut, season, ex)
                errors["base"] = "league_not_found"

        return self.async_show_form(
            step_id="custom_league",
            data_schema=vol.Schema({
                vol.Required("shortcut"): selector.TextSelector(),
                vol.Required("season"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": s, "label": s} for s in SEASONS
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )

    async def _show_team_selection(self) -> FlowResult:
        session = async_get_clientsession(self.hass)
        client = FootballApiClient(session)
        try:
            teams = await client.get_teams(self._league_shortcut, self._league_season)
            self._cached_teams = teams
        except Exception as ex:
            _LOGGER.error("Error fetching teams: %s", ex)
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required("mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "popular", "label": "Popular competition"},
                                {"value": "custom", "label": "Custom league"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }),
                errors={"base": "cannot_fetch_teams"},
            )
        return await self._finish_team_selection()

    async def _finish_team_selection(self) -> FlowResult:
        options = []
        for t in self._cached_teams:
            name = t.get("teamName", "")
            if name:
                options.append({"value": str(t["teamId"]), "label": name})

        if not options:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required("mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "popular", "label": "Popular competition"},
                                {"value": "custom", "label": "Custom league"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }),
                errors={"base": "no_teams_selected"},
            )

        return self.async_show_form(
            step_id="pick_teams",
            data_schema=vol.Schema({
                vol.Required("team_ids"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        multiple=True,
                    )
                )
            }),
            description_placeholders={"league": self._league_name},
        )

    async def async_step_pick_teams(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.async_abort(reason="no_data")

        selected = user_input.get("team_ids", [])
        if not selected:
            return self.async_show_form(
                step_id="pick_teams",
                data_schema=vol.Schema({
                    vol.Required("team_ids"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": str(t["teamId"]), "label": t.get("teamName", "")}
                                for t in self._cached_teams
                                if t.get("teamName")
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            multiple=True,
                        )
                    )
                }),
                description_placeholders={"league": self._league_name},
                errors={"base": "no_teams_selected"},
            )

        team_ids = set(str(s) for s in selected)
        teams_conf = []
        for t in self._cached_teams:
            tid = str(t["teamId"])
            if tid in team_ids:
                teams_conf.append({"team_id": t["teamId"], "team_name": t.get("teamName", "")})

        if not teams_conf:
            return self.async_abort(reason="no_teams_selected")

        entry_data = {
            "league_shortcut": self._league_shortcut,
            "league_season": self._league_season,
            "league_name": self._league_name,
            "teams": teams_conf,
        }

        return self.async_create_entry(
            title=f"Football ({self._league_name})",
            data={"entries": [entry_data]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            action = user_input["action"]
            if action == "add":
                return await self.async_step_add_league()
            if action == "remove":
                return await self.async_step_remove()
            return self.async_abort(reason="no_action")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "add", "label": "Add league/teams"},
                            {"value": "remove", "label": "Remove entry"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }),
        )

    async def async_step_add_league(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            if user_input["mode"] == "popular":
                return await self.async_step_popular_league()
            return await self.async_step_custom_league()
        return self.async_show_form(
            step_id="add_league",
            data_schema=vol.Schema({
                vol.Required("mode"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "popular", "label": "Popular competition"},
                            {"value": "custom", "label": "Custom league"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }),
        )

    async def async_step_popular_league(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._league_shortcut = user_input["shortcut"]
            self._league_season = int(user_input["season"])
            self._league_name = POPULAR_LEAGUES.get(
                self._league_shortcut, self._league_shortcut
            )
            return await self._show_team_selection()
        return self.async_show_form(
            step_id="popular_league",
            data_schema=vol.Schema({
                vol.Required("shortcut"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v}
                            for k, v in POPULAR_LEAGUES.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("season"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": s, "label": s} for s in SEASONS
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )

    async def async_step_custom_league(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            shortcut = user_input["shortcut"].strip()
            season = int(user_input["season"])
            session = async_get_clientsession(self.hass)
            client = FootballApiClient(session)
            try:
                teams = await client.get_teams(shortcut, season)
                if isinstance(teams, list) and len(teams) > 0:
                    self._league_shortcut = shortcut
                    self._league_season = season
                    self._league_name = shortcut
                    self._cached_teams = teams
                    return await self._finish_team_selection()
                errors["base"] = "league_not_found"
            except Exception as ex:
                _LOGGER.error("Error validating league %s/%s: %s", shortcut, season, ex)
                errors["base"] = "league_not_found"
        return self.async_show_form(
            step_id="custom_league",
            data_schema=vol.Schema({
                vol.Required("shortcut"): selector.TextSelector(),
                vol.Required("season"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": s, "label": s} for s in SEASONS
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )

    async def _show_team_selection(self) -> FlowResult:
        session = async_get_clientsession(self.hass)
        client = FootballApiClient(session)
        try:
            teams = await client.get_teams(self._league_shortcut, self._league_season)
            self._cached_teams = teams
        except Exception as ex:
            _LOGGER.error("Error fetching teams: %s", ex)
            return self.async_show_form(
                step_id="add_league",
                data_schema=vol.Schema({
                    vol.Required("mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "popular", "label": "Popular competition"},
                                {"value": "custom", "label": "Custom league"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }),
                errors={"base": "cannot_fetch_teams"},
            )
        return await self._finish_team_selection()

    async def _finish_team_selection(self) -> FlowResult:
        options = []
        for t in self._cached_teams:
            name = t.get("teamName", "")
            if name:
                options.append({"value": str(t["teamId"]), "label": name})

        if not options:
            return self.async_show_form(
                step_id="add_league",
                data_schema=vol.Schema({
                    vol.Required("mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "popular", "label": "Popular competition"},
                                {"value": "custom", "label": "Custom league"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }),
                errors={"base": "no_teams_selected"},
            )

        return self.async_show_form(
            step_id="pick_teams",
            data_schema=vol.Schema({
                vol.Required("team_ids"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        multiple=True,
                    )
                )
            }),
            description_placeholders={"league": self._league_name},
        )

    async def async_step_pick_teams(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.async_abort(reason="no_data")

        selected = user_input.get("team_ids", [])
        if not selected:
            return self.async_show_form(
                step_id="pick_teams",
                data_schema=vol.Schema({
                    vol.Required("team_ids"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": str(t["teamId"]), "label": t.get("teamName", "")}
                                for t in self._cached_teams
                                if t.get("teamName")
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            multiple=True,
                        )
                    )
                }),
                description_placeholders={"league": self._league_name},
                errors={"base": "no_teams_selected"},
            )

        team_ids = set(str(s) for s in selected)
        teams_conf = []
        for t in self._cached_teams:
            tid = str(t["teamId"])
            if tid in team_ids:
                teams_conf.append({"team_id": t["teamId"], "team_name": t.get("teamName", "")})

        if not teams_conf:
            return self.async_abort(reason="no_teams_selected")

        entries = list(self.entry.data.get("entries", []))
        entries.append({
            "league_shortcut": self._league_shortcut,
            "league_season": self._league_season,
            "league_name": self._league_name,
            "teams": teams_conf,
        })
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, "entries": entries}
        )
        return self.async_create_entry(title="", data={})

    async def async_step_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            indices = sorted(
                (int(i) for i in user_input.get("indices", [])), reverse=True
            )
            entries = list(self.entry.data.get("entries", []))
            for idx in indices:
                if idx < len(entries):
                    entries.pop(idx)
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "entries": entries}
            )
            return self.async_create_entry(title="", data={})

        entries = self.entry.data.get("entries", [])
        if not entries:
            return self.async_abort(reason="no_entries")

        options = [
            {"value": str(i), "label": _entry_label(e)}
            for i, e in enumerate(entries)
        ]

        return self.async_show_form(
            step_id="remove",
            data_schema=vol.Schema({
                vol.Required("indices"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        multiple=True,
                    )
                )
            }),
        )
