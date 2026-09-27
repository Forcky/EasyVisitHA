"""Polls EasyVisit availability and announces newly available slots."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EasyVisitApiClient, EasyVisitApiError
from .const import (
    ANY_DOCTOR,
    BOOKING_URL,
    CONF_APPT_TYPE_ID,
    CONF_LOCATION_ID,
    CONF_LOCATION_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_SCAN_INTERVAL,
    CONF_WATCHES,
    DEFAULT_CUTOFF_DAYS,
    DEFAULT_CUTOFF_DAYS_ANY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_SLOT_AVAILABLE,
    NOTIFY_MAX_SLOTS,
    STORAGE_VERSION,
)
from .slots import (
    Slot,
    cutoff_date,
    diff_seen,
    format_date,
    format_slot,
    parse_resources,
    qualifying,
    slots_for_watch,
)

_LOGGER = logging.getLogger(__name__)

_SAVE_DELAY = 10  # seconds


class EasyVisitCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One resources call per poll covers every watched doctor.

    coordinator.data = {
        "doctors": {resourceId: {name, notes, manual_confirm, appointment_length}},
        "watches": {watch_id: {"slots": [Slot], "qualifying": [Slot],
                               "cutoff": date}},
    }
    """

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: EasyVisitApiClient
    ) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=dt.timedelta(minutes=minutes),
        )
        self.client = client
        self.location_id: int = entry.data[CONF_LOCATION_ID]
        self.appt_type_id: int = entry.data[CONF_APPT_TYPE_ID]
        self.location_name: str = entry.data.get(CONF_LOCATION_NAME, "")
        self.booking_url = BOOKING_URL.format(
            location_id=self.location_id, appt_type_id=self.appt_type_id
        )
        self.watches: dict[int, str] = {
            int(k): v for k, v in entry.options.get(CONF_WATCHES, {}).items()
        }
        self.tz: dt.tzinfo = dt_util.get_default_time_zone()
        self.last_checked: dt.datetime | None = None
        self.practice_device_id: str | None = None  # set in async_setup_entry

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        # {watch_id: {"cutoff_days": int, "notify": bool, "seen": set[str] | None}}
        # seen is None until the watch's first poll (see _announce).
        self._state: dict[int, dict[str, Any]] = {}

    # ---- persisted per-watch settings -------------------------------------

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        saved = stored.get("watches", {})
        for wid in self.watches:
            item = saved.get(str(wid), {})
            seen = item.get("seen")
            default_cutoff = DEFAULT_CUTOFF_DAYS_ANY if wid == ANY_DOCTOR else DEFAULT_CUTOFF_DAYS
            self._state[wid] = {
                "cutoff_days": int(item.get("cutoff_days", default_cutoff)),
                # "Any doctor" is noisy, so it starts muted.
                "notify": bool(item.get("notify", wid != ANY_DOCTOR)),
                "seen": set(seen) if seen is not None else None,
            }

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "watches": {
                str(wid): {
                    "cutoff_days": st["cutoff_days"],
                    "notify": st["notify"],
                    "seen": sorted(st["seen"]) if st["seen"] is not None else None,
                }
                for wid, st in self._state.items()
            }
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._data_to_save, _SAVE_DELAY)

    async def async_save_now(self) -> None:
        """Write pending settings immediately (on unload/reload)."""
        await self._store.async_save(self._data_to_save())

    def get_cutoff_days(self, wid: int) -> int:
        return self._state[wid]["cutoff_days"]

    async def async_set_cutoff_days(self, wid: int, days: int) -> None:
        self._state[wid]["cutoff_days"] = days
        self._save()
        # Recompute now; slots newly inside the window are announced.
        await self.async_request_refresh()

    def get_notify(self, wid: int) -> bool:
        return self._state[wid]["notify"]

    def set_notify(self, wid: int, on: bool) -> None:
        self._state[wid]["notify"] = on
        self._save()
        self.async_update_listeners()

    # ---- polling -----------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            resources = await self.client.get_resources(self.location_id, self.appt_type_id)
        except EasyVisitApiError as err:
            raise UpdateFailed(str(err)) from err

        doctors, all_slots = parse_resources(resources, dt_util.get_default_time_zone())
        if all_slots:
            self.tz = all_slots[0].start.tzinfo  # the practice's own zone
        now = dt_util.utcnow()
        self.last_checked = now

        watches: dict[int, dict[str, Any]] = {}
        for wid in self.watches:
            st = self._state[wid]
            slots = slots_for_watch(all_slots, wid)
            match = qualifying(slots, now, st["cutoff_days"], self.tz)
            watches[wid] = {
                "slots": slots,
                "qualifying": match,
                "cutoff": cutoff_date(now, st["cutoff_days"], self.tz),
            }
            await self._announce(wid, match, watches[wid]["cutoff"])

        return {"doctors": doctors, "watches": watches}

    async def _announce(self, wid: int, match: list[Slot], cutoff: dt.date) -> None:
        st = self._state[wid]
        if st["seen"] is None:
            # First poll for a new watch: remember what's already there without
            # announcing it, so adding the integration doesn't send a burst.
            st["seen"] = {s.key for s in match}
            self._save()
            return

        new, seen = diff_seen(match, st["seen"])
        if seen != st["seen"]:
            st["seen"] = seen
            self._save()
        if not new:
            return

        _LOGGER.info(
            "%s: %d new slot(s) by %s", self.watches[wid], len(new), cutoff.isoformat()
        )
        self.hass.bus.async_fire(
            EVENT_SLOT_AVAILABLE,
            {
                "entry_id": self.config_entry.entry_id,
                "location_id": self.location_id,
                "appt_type_id": self.appt_type_id,
                "watch_id": wid,
                "watch_name": self.watches[wid],
                "cutoff": cutoff.isoformat(),
                "new_slots": [s.as_dict() for s in new],
                "booking_url": self.booking_url,
            },
        )
        if st["notify"]:
            await self.async_notify(wid, new, match, cutoff)

    # ---- notifications -----------------------------------------------------

    async def async_notify(
        self,
        wid: int,
        new: list[Slot],
        match: list[Slot],
        cutoff: dt.date,
        test: bool = False,
    ) -> None:
        targets: list[str] = self.config_entry.options.get(CONF_NOTIFY_TARGETS, [])
        if not targets:
            _LOGGER.debug("No notify targets configured")
            return

        name = self.watches[wid]
        any_doctor = wid == ANY_DOCTOR
        by = format_date(cutoff)
        if new:
            count = len(new)
            title = f"{name}: {count} new slot{'s' if count != 1 else ''} by {by}"
            lines = [format_slot(s, self.tz, any_doctor) for s in new[:NOTIFY_MAX_SLOTS]]
            if count > NOTIFY_MAX_SLOTS:
                lines.append(f"+{count - NOTIFY_MAX_SLOTS} more")
            if len(match) > count:
                lines.append(f"({len(match)} open by {by} in total)")
            message = "\n".join(lines)
        else:
            title = f"{name}: nothing open by {by}"
            message = "No slots before the cutoff right now."
        if test:
            title = f"[Test] {title}"

        data = {
            "url": self.booking_url,  # HA companion app, iOS
            "clickAction": self.booking_url,  # HA companion app, Android
            "tag": f"{DOMAIN}_{self.config_entry.entry_id}_{wid}",
            "group": DOMAIN,
        }
        for target in targets:
            domain, _, service = target.partition(".")
            if domain != "notify" or not service:
                # The config flow only accepts notify.<service>; never call
                # anything else, whatever ended up in the options.
                _LOGGER.warning("Ignoring notify target %r: not a notify service", target)
                continue
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {"title": title, "message": message, "data": data},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001 - one bad target shouldn't stop the others
                _LOGGER.exception("Sending notification via %s failed", target)

    async def async_send_test(self, wid: int) -> None:
        """Send what is currently open before the cutoff, ignoring 'seen'."""
        watch = (self.data or {}).get("watches", {}).get(wid)
        if watch is None:
            return
        match = watch["qualifying"]
        await self.async_notify(wid, match, match, watch["cutoff"], test=True)
