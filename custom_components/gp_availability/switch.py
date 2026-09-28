"""Switch: send notifications for this watch."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GpAvailabilityConfigEntry
from .coordinator import GpAvailabilityCoordinator
from .entity import GpAvailabilityWatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GpAvailabilityConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(NotifySwitch(coordinator, wid) for wid in coordinator.watches)


class NotifySwitch(GpAvailabilityWatchEntity, SwitchEntity):
    """State lives in the coordinator's Store, so it survives restarts."""

    def __init__(self, coordinator: GpAvailabilityCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id, "notifications")

    @property
    def available(self) -> bool:
        return True  # a setting, usable even while the API is down

    @property
    def is_on(self) -> bool:
        return self.coordinator.get_notify(self.watch_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_notify(self.watch_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_notify(self.watch_id, False)
