"""Binary sensor: is anything open before the cutoff?"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EasyVisitConfigEntry
from .coordinator import EasyVisitCoordinator
from .entity import EasyVisitWatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EasyVisitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SlotBeforeCutoff(coordinator, wid) for wid in coordinator.watches)


class SlotBeforeCutoff(EasyVisitWatchEntity, BinarySensorEntity):
    def __init__(self, coordinator: EasyVisitCoordinator, watch_id: int) -> None:
        super().__init__(coordinator, watch_id, "slot_before_cutoff")

    @property
    def is_on(self) -> bool | None:
        watch = self.watch
        return bool(watch["qualifying"]) if watch else None
