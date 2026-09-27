"""EasyVisit GP availability for Home Assistant.

Watches a practice's EasyVisit booking page for open appointments with chosen
doctors and notifies when one opens up before a cutoff date.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EasyVisitApiClient
from .const import DOMAIN
from .coordinator import EasyVisitCoordinator
from .entity import practice_device

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

type EasyVisitConfigEntry = ConfigEntry[EasyVisitCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EasyVisitConfigEntry) -> bool:
    """Set up EasyVisit from a config entry."""
    client = EasyVisitApiClient(async_get_clientsession(hass))
    coordinator = EasyVisitCoordinator(hass, entry, client)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Doctor devices hang off the practice device, so it must exist first.
    registry = dr.async_get(hass)
    coordinator.practice_device_id = registry.async_get_or_create(
        config_entry_id=entry.entry_id, **practice_device(coordinator)
    ).id

    # Drop devices for doctors no longer watched (removed in the options flow).
    wanted = {(DOMAIN, entry.entry_id)} | {
        (DOMAIN, f"{entry.entry_id}_{wid}") for wid in coordinator.watches
    }
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not device.identifiers & wanted:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: EasyVisitConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EasyVisitConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save_now()
    return unloaded
