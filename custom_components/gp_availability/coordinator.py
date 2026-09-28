"""Polls a practice's availability and announces newly available slots."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ANY_DOCTOR,
    CONF_APPT_TYPE_ID,
    CONF_BOOKING_URL,
    CONF_NOTIFY_TARGETS,
    CONF_PRACTICE_ID,
    CONF_PRACTICE_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TIMEZONE,
    CONF_WATCHES,
    DEFAULT_CUTOFF_DAYS,
    DEFAULT_CUTOFF_DAYS_ANY,
    DOMAIN,
    EVENT_SLOT_AVAILABLE,
    NOTIFY_MAX_SLOTS,
    STORAGE_VERSION,
)
from .providers import Doctor, Provider, ProviderError
from .slots import (
    Slot,
    cutoff_date,
    diff_seen,
    format_date,
    format_slot,
    qualifying,
    slots_for_watch,
)

_LOGGER = logging.getLogger(__name__)

_SAVE_DELAY = 10  # seconds


class GpAvailabilityCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One provider fetch per poll covers every watched doctor.

    coordinator.data = {
        "doctors": {doctor_id: Doctor},
        "watches": {watch_id: {"slots": [Slot], "qualifying": [Slot],
                               "cutoff": date, "next_available": datetime | None,
                               "url": str}},
    }
    """

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, provider: Provider) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, provider.default_scan_interval)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=dt.timedelta(minutes=max(minutes, provider.min_scan_interval)),
        )
        self.provider = provider
        self.practice_id: str = entry.data[CONF_PRACTICE_ID]
        self.appt_type_id: str = entry.data[CONF_APPT_TYPE_ID]
        self.practice_name: str = entry.data.get(CONF_PRACTICE_NAME, "")
        self.booking_url: str = entry.data[CONF_BOOKING_URL]
        self.watches: dict[str, str] = dict(entry.options.get(CONF_WATCHES, {}))
        zone = entry.data.get(CONF_TIMEZONE)
        self.tz: dt.tzinfo = ZoneInfo(zone) if zone else dt_util.get_default_time_zone()
        self.last_checked: dt.datetime | None = None
        self.practice_device_id: str | None = None  # set in async_setup_entry

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        # {watch_id: {"cutoff_days": int, "notify": bool, "seen": set[str] | None}}
        # seen is None until the watch's first poll (see _announce).
        self._state: dict[str, dict[str, Any]] = {}

    # ---- persisted per-watch settings -------------------------------------

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        saved = stored.get("watches", {})
        for wid in self.watches:
            item = saved.get(wid, {})
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
                wid: {
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

    def get_cutoff_days(self, wid: str) -> int:
        return self._state[wid]["cutoff_days"]

    async def async_set_cutoff_days(self, wid: str, days: int) -> None:
        self._state[wid]["cutoff_days"] = days
        self._save()
        # Recompute now; slots newly inside the window are announced.
        await self.async_request_refresh()

    def get_notify(self, wid: str) -> bool:
        return self._state[wid]["notify"]

    def set_notify(self, wid: str, on: bool) -> None:
        self._state[wid]["notify"] = on
        self._save()
        self.async_update_listeners()

    # ---- polling -----------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        # Fetch far enough for the longest cutoff; some providers page by date.
        until = max(
            (cutoff_date(now, st["cutoff_days"], self.tz) for st in self._state.values()),
            default=now.astimezone(self.tz).date(),
        )
        wanted = None if ANY_DOCTOR in self.watches else set(self.watches)
        try:
            found = await self.provider.fetch(
                self.practice_id, self.appt_type_id, wanted, until, self.tz
            )
        except ProviderError as err:
            raise UpdateFailed(str(err)) from err

        if found.slots:
            self.tz = found.slots[0].start.tzinfo  # the practice's own zone
        self.last_checked = now

        watches: dict[str, dict[str, Any]] = {}
        for wid in self.watches:
            st = self._state[wid]
            slots = slots_for_watch(found.slots, wid)
            match = qualifying(slots, now, st["cutoff_days"], self.tz)
            doctor = found.doctors.get(wid)
            watches[wid] = {
                "slots": slots,
                "qualifying": match,
                "cutoff": cutoff_date(now, st["cutoff_days"], self.tz),
                "next_available": _next_available(wid, slots, found.doctors),
                "url": (doctor.url if doctor and doctor.url else None) or self.booking_url,
            }
            await self._announce(wid, match, watches[wid])

        return {"doctors": found.doctors, "watches": watches}

    async def _announce(self, wid: str, match: list[Slot], watch: dict[str, Any]) -> None:
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

        cutoff: dt.date = watch["cutoff"]
        _LOGGER.info(
            "%s: %d new slot(s) by %s", self.watches[wid], len(new), cutoff.isoformat()
        )
        self.hass.bus.async_fire(
            EVENT_SLOT_AVAILABLE,
            {
                "entry_id": self.config_entry.entry_id,
                "provider": self.provider.key,
                "practice_id": self.practice_id,
                "appt_type_id": self.appt_type_id,
                "watch_id": wid,
                "watch_name": self.watches[wid],
                "cutoff": cutoff.isoformat(),
                "new_slots": [s.as_dict() for s in new],
                "booking_url": watch["url"],
            },
        )
        if st["notify"]:
            await self.async_notify(wid, new, match, cutoff, watch["url"])

    # ---- notifications -----------------------------------------------------

    async def async_notify(
        self,
        wid: str,
        new: list[Slot],
        match: list[Slot],
        cutoff: dt.date,
        url: str,
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
            "url": url,  # HA companion app, iOS
            "clickAction": url,  # HA companion app, Android
            "tag": f"{DOMAIN}_{self.config_entry.entry_id}_{wid}",
            "group": DOMAIN,
            # Slots go fast. Without these, a sleeping Android phone batches the
            # push (Doze) and it can arrive tens of minutes late.
            "priority": "high",  # Android
            "ttl": 0,  # Android
            "push": {"interruption-level": "time-sensitive"},  # iOS
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

    async def async_send_test(self, wid: str) -> None:
        """Send what is currently open before the cutoff, ignoring 'seen'."""
        watch = (self.data or {}).get("watches", {}).get(wid)
        if watch is None:
            return
        match = watch["qualifying"]
        await self.async_notify(wid, match, match, watch["cutoff"], watch["url"], test=True)


def _next_available(
    wid: str, slots: list[Slot], doctors: dict[str, Doctor]
) -> dt.datetime | None:
    """The earliest open time, even when it is beyond what was fetched."""
    if slots:
        return slots[0].start
    pool = doctors.values() if wid == ANY_DOCTOR else [doctors[wid]] if wid in doctors else []
    times = [d.next_available for d in pool if d.next_available]
    return min(times) if times else None
