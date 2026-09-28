"""Number: how many days ahead counts as soon enough."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GpAvailabilityConfigEntry
from .const import MAX_CUTOFF_DAYS, MIN_CUTOFF_DAYS
from .coordinator import GpAvailabilityCoordinator
from .entity import GpAvailabilityWatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GpAvailabilityConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(CutoffDays(coordinator, wid) for wid in coordinator.watches)


class CutoffDays(GpAvailabilityWatchEntity, NumberEntity):
    """0 = today only, 14 = anything up to two weeks from today."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_CUTOFF_DAYS
    _attr_native_max_value = MAX_CUTOFF_DAYS
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    def __init__(self, coordinator: GpAvailabilityCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id, "cutoff_days")

    @property
    def available(self) -> bool:
        return True  # a setting, usable even while the API is down

    @property
    def native_value(self) -> float:
        return self.coordinator.get_cutoff_days(self.watch_id)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_cutoff_days(self.watch_id, int(value))
