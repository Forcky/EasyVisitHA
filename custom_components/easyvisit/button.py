"""Button: send a test notification listing what is open before the cutoff."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
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
    async_add_entities(TestNotifyButton(coordinator, wid) for wid in coordinator.watches)


class TestNotifyButton(EasyVisitWatchEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EasyVisitCoordinator, watch_id: int) -> None:
        super().__init__(coordinator, watch_id, "test_notification")

    async def async_press(self) -> None:
        await self.coordinator.async_send_test(self.watch_id)
