from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FootballApiClient
from .const import DOMAIN

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

SEASONS = {"2024": "2024", "2025": "2025", "2026": "2026"}


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
            data_schema=vol.Schema(
                {
                    vol.Required("mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "popular", "label": "Popular competition"},
                                {"value": "custom", "label": "Custom league"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_popular_league(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._shortcut = user_input["shortcut"]
            self._season = int(user_input["season"])
            self._league_name = POPULAR_LEAGUES.get(
                self._shortcut, self._shortcut
            )
            return await self.async_step_pick_teams()

        return self.async_show_form(
            step_id="popular_league",
            data_schema=vol.Schema(
                {
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
                                {"value": k, "label": v}
                                for k, v in SEASONS.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
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
            if await client.validate_league(shortcut, season):
                self._shortcut = shortcut
                self._season = season
                self._league_name = shortcut
                return await self.async_step_pick_teams()
            errors["base"] = "league_not_found"

        return self.async_show_form(
            step_id="custom_league",
            data_schema=vol.Schema(
                {
                    vol.Required("shortcut"): selector.TextSelector(),
                    vol.Required("season"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": k, "label": v}
                                for k, v in SEASONS.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_pick_teams(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get("team_ids", [])
            if not selected:
                errors["base"] = "no_teams_selected"
            else:
                teams_conf = [
                    {"team_id": t["teamId"], "team_name": t["teamName"]}
                    for t in self._cached_teams
                    if str(t["teamId"]) in selected
                ]
                if not teams_conf:
                    errors["base"] = "no_teams_selected"
                else:
                    entry_data = {
                        "league_shortcut": self._shortcut,
                        "league_season": self._season,
                        "league_name": self._league_name,
                        "teams": teams_conf,
                    }

                    if self.source == config_entries.SOURCE_OPTIONS_FLOW:
                        entries = list(self.config_entry.data.get("entries", []))
                        entries.append(entry_data)
                        self.hass.config_entries.async_update_entry(
                            self.config_entry,
                            data={**self.config_entry.data, "entries": entries},
                        )
                        return self.async_create_entry(title="", data={})

                    return self.async_create_entry(
                        title=f"Football ({self._league_name})",
                        data={"entries": [entry_data]},
                    )

        if not errors:
            session = async_get_clientsession(self.hass)
            client = FootballApiClient(session)
            try:
                teams = await client.get_teams(self._shortcut, self._season)
            except Exception:
                errors["base"] = "cannot_fetch_teams"
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(
                        {
                            vol.Required("mode"): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    options=[
                                        {"value": "popular", "label": "Popular competition"},
                                        {"value": "custom", "label": "Custom league"},
                                    ],
                                    mode=selector.SelectSelectorMode.LIST,
                                )
                            )
                        }
                    ),
                    errors=errors,
                )

            teams = [t for t in teams if t.get("teamName")]
            self._cached_teams = teams

            if self.source == config_entries.SOURCE_OPTIONS_FLOW:
                existing_ids = set()
                for e in self.config_entry.data.get("entries", []):
                    if (
                        e.get("league_shortcut") == self._shortcut
                        and e.get("league_season") == self._season
                    ):
                        for t in e.get("teams", []):
                            existing_ids.add(t["team_id"])
            else:
                existing_ids = set()

            options = [
                {
                    "value": str(t["teamId"]),
                    "label": (
                        f"{t['teamName']} ✓"
                        if t["teamId"] in existing_ids
                        else t["teamName"]
                    ),
                }
                for t in teams
            ]

            return self.async_show_form(
                step_id="pick_teams",
                data_schema=vol.Schema(
                    {
                        vol.Optional("team_ids", default=[]): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=options,
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                multiple=True,
                            )
                        )
                    }
                ),
                description_placeholders={"league": self._league_name},
                errors=errors,
            )

        return self.async_show_form(
            step_id="pick_teams",
            data_schema=vol.Schema(
                {
                    vol.Optional("team_ids", default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": str(t["teamId"]), "label": t["teamName"]}
                                for t in self._cached_teams
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            multiple=True,
                        )
                    )
                }
            ),
            description_placeholders={"league": self._league_name},
            errors=errors,
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
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "add", "label": "Add league/teams"},
                                {"value": "remove", "label": "Remove entry"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
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
            data_schema=vol.Schema(
                {
                    vol.Required("mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": "popular", "label": "Popular competition"},
                                {"value": "custom", "label": "Custom league"},
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_popular_league(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._shortcut = user_input["shortcut"]
            self._season = int(user_input["season"])
            self._league_name = POPULAR_LEAGUES.get(
                self._shortcut, self._shortcut
            )
            return await self.async_step_pick_teams()
        return self.async_show_form(
            step_id="popular_league",
            data_schema=vol.Schema(
                {
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
                                {"value": k, "label": v}
                                for k, v in SEASONS.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
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
            if await client.validate_league(shortcut, season):
                self._shortcut = shortcut
                self._season = season
                self._league_name = shortcut
                return await self.async_step_pick_teams()
            errors["base"] = "league_not_found"
        return self.async_show_form(
            step_id="custom_league",
            data_schema=vol.Schema(
                {
                    vol.Required("shortcut"): selector.TextSelector(),
                    vol.Required("season"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": k, "label": v}
                                for k, v in SEASONS.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_pick_teams(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get("team_ids", [])
            if not selected:
                errors["base"] = "no_teams_selected"
            else:
                teams_conf = [
                    {"team_id": t["teamId"], "team_name": t["teamName"]}
                    for t in self._cached_teams
                    if str(t["teamId"]) in selected
                ]
                if not teams_conf:
                    errors["base"] = "no_teams_selected"
                else:
                    entries = list(self.entry.data.get("entries", []))
                    entries.append(
                        {
                            "league_shortcut": self._shortcut,
                            "league_season": self._season,
                            "league_name": self._league_name,
                            "teams": teams_conf,
                        }
                    )
                    self.hass.config_entries.async_update_entry(
                        self.entry, data={**self.entry.data, "entries": entries}
                    )
                    return self.async_create_entry(title="", data={})

        if not errors:
            session = async_get_clientsession(self.hass)
            client = FootballApiClient(session)
            try:
                teams = await client.get_teams(self._shortcut, self._season)
            except Exception:
                errors["base"] = "cannot_fetch_teams"

        if errors:
            return self.async_show_form(
                step_id="add_league",
                data_schema=vol.Schema(
                    {
                        vol.Required("mode"): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    {"value": "popular", "label": "Popular competition"},
                                    {"value": "custom", "label": "Custom league"},
                                ],
                                mode=selector.SelectSelectorMode.LIST,
                            )
                        )
                    }
                ),
                errors=errors,
            )

        teams = [t for t in teams if t.get("teamName")]
        self._cached_teams = teams

        existing_ids = set()
        for e in self.entry.data.get("entries", []):
            if (
                e.get("league_shortcut") == self._shortcut
                and e.get("league_season") == self._season
            ):
                for t in e.get("teams", []):
                    existing_ids.add(t["team_id"])

        options = [
            {
                "value": str(t["teamId"]),
                "label": (
                    f"{t['teamName']} ✓"
                    if t["teamId"] in existing_ids
                    else t["teamName"]
                ),
            }
            for t in teams
        ]

        return self.async_show_form(
            step_id="pick_teams",
            data_schema=vol.Schema(
                {
                    vol.Optional("team_ids", default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            multiple=True,
                        )
                    )
                }
            ),
            description_placeholders={"league": self._league_name},
        )

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
            data_schema=vol.Schema(
                {
                    vol.Required("indices"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            multiple=True,
                        )
                    )
                }
            ),
        )
