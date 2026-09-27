"""Base entity: one device per watched doctor, under a practice device."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ANY_DOCTOR, DOMAIN
from .coordinator import EasyVisitCoordinator


def practice_device(coordinator: EasyVisitCoordinator) -> DeviceInfo:
    entry = coordinator.config_entry
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=coordinator.location_name or entry.title,
        manufacturer="EasyVisit",
        model=entry.title,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=coordinator.booking_url,
    )


class EasyVisitWatchEntity(CoordinatorEntity[EasyVisitCoordinator]):
    """An entity belonging to one watch (a doctor, or any doctor)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EasyVisitCoordinator, watch_id: int, key: str) -> None:
        super().__init__(coordinator)
        self.watch_id = watch_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{watch_id}_{key}"
        self._attr_translation_key = key
        name = coordinator.watches[watch_id]
        if watch_id == ANY_DOCTOR:
            name = f"Any doctor at {coordinator.location_name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{watch_id}")},
            name=name,
            manufacturer="EasyVisit",
            model=coordinator.location_name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.booking_url,
            via_device_id=coordinator.practice_device_id,
        )

    @property
    def watch(self) -> dict | None:
        return (self.coordinator.data or {}).get("watches", {}).get(self.watch_id)
