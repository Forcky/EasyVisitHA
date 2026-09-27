"""Sensors: next available slot, slots before the cutoff, last checked."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EasyVisitConfigEntry
from .const import ANY_DOCTOR, ATTR_MAX_SLOTS
from .coordinator import EasyVisitCoordinator
from .entity import EasyVisitWatchEntity, practice_device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EasyVisitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [LastCheckedSensor(coordinator)]
    for wid in coordinator.watches:
        entities.append(NextAvailableSensor(coordinator, wid))
        entities.append(SlotsBeforeCutoffSensor(coordinator, wid))
    async_add_entities(entities)


class NextAvailableSensor(EasyVisitWatchEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: EasyVisitCoordinator, watch_id: int) -> None:
        super().__init__(coordinator, watch_id, "next_available")

    @property
    def native_value(self) -> datetime | None:
        watch = self.watch
        return watch["slots"][0].start if watch and watch["slots"] else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        watch = self.watch or {"slots": []}
        attrs: dict[str, Any] = {
            "open_slots": len(watch["slots"]),
            "next_slots": [s.as_dict() for s in watch["slots"][:ATTR_MAX_SLOTS]],
            "booking_url": self.coordinator.booking_url,
        }
        if self.watch_id != ANY_DOCTOR:
            doctor = (self.coordinator.data or {}).get("doctors", {}).get(self.watch_id)
            if doctor:
                attrs["notes"] = doctor["notes"]
                attrs["manual_confirm"] = doctor["manual_confirm"]
            else:
                attrs["notes"] = "Not listed for this appointment type right now"
        return attrs


class SlotsBeforeCutoffSensor(EasyVisitWatchEntity, SensorEntity):
    _attr_native_unit_of_measurement = "slots"

    def __init__(self, coordinator: EasyVisitCoordinator, watch_id: int) -> None:
        super().__init__(coordinator, watch_id, "slots_before_cutoff")

    @property
    def native_value(self) -> int | None:
        watch = self.watch
        return len(watch["qualifying"]) if watch else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        watch = self.watch
        if not watch:
            return {}
        return {
            "cutoff": watch["cutoff"].isoformat(),
            "slots": [s.as_dict() for s in watch["qualifying"][:ATTR_MAX_SLOTS]],
        }


class LastCheckedSensor(CoordinatorEntity[EasyVisitCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "last_checked"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EasyVisitCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_last_checked"
        self._attr_device_info = practice_device(coordinator)

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_checked
