from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_TYPES
from .coordinator import FootballDataUpdateCoordinator

STATUS_LABELS = {
    "NS": "Scheduled",
    "PRE_GAME": "Pre-game",
    "LIVE": "Live",
    "HALF_TIME": "Half Time",
    "FT": "Finished",
    "POSTPONED": "Postponed",
    "CANCELLED": "Cancelled",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FootballDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[FootballSensor] = []

    for entry_conf in entry.data.get("entries", []):
        shortcut = entry_conf["league_shortcut"]
        for team in entry_conf.get("teams", []):
            team_key = f"{shortcut}_{team['team_id']}"
            label = team["team_name"]
            for sensor_type in SENSOR_TYPES:
                entities.append(
                    FootballSensor(coordinator, team_key, sensor_type, label)
                )

    async_add_entities(entities)


class FootballSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        coordinator: FootballDataUpdateCoordinator,
        team_key: str,
        sensor_type: str,
        label: str,
    ) -> None:
        super().__init__(coordinator)
        self._team_key = team_key
        self._sensor_type = sensor_type
        config = SENSOR_TYPES[sensor_type]
        self._attr_name = f"{label} {config['name']}"
        self._attr_unique_id = f"football_{team_key}_{sensor_type}"
        self._attr_icon = config["icon"]
        self._attr_should_poll = False

    @property
    def native_value(self) -> Any:
        data = (
            self.coordinator.data.get(self._team_key)
            if self.coordinator.data
            else None
        )
        if data is None:
            return None
        if "error" in data:
            return data["error"]

        if self._sensor_type == "status":
            raw = data.get("status", "")
            return STATUS_LABELS.get(raw, raw)
        if self._sensor_type == "team_score":
            return data.get("our_score")
        if self._sensor_type == "opponent_score":
            return data.get("opponent_score")
        return data.get(self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = (
            self.coordinator.data.get(self._team_key)
            if self.coordinator.data
            else None
        )
        if data is None:
            return {}
        return {
            k: data[k]
            for k in ("fixture_id", "timestamp", "date", "team_name", "is_live")
            if k in data
        }
