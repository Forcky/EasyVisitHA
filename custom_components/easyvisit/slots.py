"""Slot parsing and matching.

Kept free of Home Assistant imports so the logic can be unit-tested with
plain pytest.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .const import ANY_DOCTOR

# EasyVisit reports each day's zone as a Windows time zone name. Slot times are
# naive local times in that zone.
_WINDOWS_TZ = {
    "Tasmania Standard Time": "Australia/Hobart",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "E. Australia Standard Time": "Australia/Brisbane",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "AUS Central Standard Time": "Australia/Darwin",
    "W. Australia Standard Time": "Australia/Perth",
}


@dataclass(frozen=True, order=True)
class Slot:
    """One bookable appointment time."""

    start: dt.datetime  # timezone-aware; first so slots sort by time
    resource_id: int
    resource_name: str

    @property
    def key(self) -> str:
        """Stable identity used to remember which slots were already announced."""
        return f"{self.resource_id}|{self.start.replace(tzinfo=None).isoformat()}"

    @property
    def api_datetime(self) -> str:
        """The naive local string the booking endpoints expect."""
        return self.start.replace(tzinfo=None).isoformat()

    def as_dict(self) -> dict[str, Any]:
        return {
            "doctor": self.resource_name,
            "resource_id": self.resource_id,
            "start": self.start.isoformat(),
        }


def zone_for(windows_name: str | None, default: dt.tzinfo) -> dt.tzinfo:
    """Map an EasyVisit (Windows) time zone name to a tzinfo."""
    iana = _WINDOWS_TZ.get(windows_name or "")
    return ZoneInfo(iana) if iana else default


def parse_resources(
    resources: Iterable[dict[str, Any]], default_tz: dt.tzinfo
) -> tuple[dict[int, dict[str, Any]], list[Slot]]:
    """Return ({resourceId: doctor info}, all slots sorted by time)."""
    doctors: dict[int, dict[str, Any]] = {}
    slots: list[Slot] = []
    for res in resources:
        rid = int(res["resourceId"])
        name = (res.get("name") or f"Resource {rid}").strip()
        doctors[rid] = {
            "name": name,
            "notes": (res.get("notesForPatients") or "").strip(),
            "manual_confirm": bool(res.get("manualConfirm")),
            "appointment_length": res.get("appointmentLength"),
        }
        for day in res.get("availableSlotDates") or []:
            tz = zone_for(day.get("timeZoneId"), default_tz)
            for raw in day.get("slots") or []:
                start = dt.datetime.fromisoformat(raw["dateTime"])
                if start.tzinfo is None:
                    start = start.replace(tzinfo=tz)
                slots.append(Slot(start, int(raw.get("resourceId", rid)), name))
    slots.sort()
    return doctors, slots


def slots_for_watch(slots: Iterable[Slot], watch_id: int) -> list[Slot]:
    """Slots belonging to one doctor, or all of them for ANY_DOCTOR."""
    if watch_id == ANY_DOCTOR:
        return list(slots)
    return [s for s in slots if s.resource_id == watch_id]


def cutoff_date(now: dt.datetime, cutoff_days: int, tz: dt.tzinfo) -> dt.date:
    """Last calendar day (inclusive) that counts as 'soon enough'."""
    return now.astimezone(tz).date() + dt.timedelta(days=cutoff_days)


def qualifying(
    slots: Iterable[Slot], now: dt.datetime, cutoff_days: int, tz: dt.tzinfo
) -> list[Slot]:
    """Future slots falling on or before the cutoff date."""
    last_day = cutoff_date(now, cutoff_days, tz)
    return [s for s in slots if s.start > now and s.start.astimezone(tz).date() <= last_day]


def diff_seen(
    current: Iterable[Slot], seen: set[str]
) -> tuple[list[Slot], set[str]]:
    """Return (slots not announced before, the new seen set).

    The new seen set is exactly the current qualifying keys, so a slot that
    disappears (someone booked it) and later reopens is announced again.
    """
    current = list(current)
    new = [s for s in current if s.key not in seen]
    return new, {s.key for s in current}


def format_slot(slot: Slot, tz: dt.tzinfo, with_doctor: bool = False) -> str:
    """Short human form, e.g. 'Tue 7 Oct 10:15'."""
    local = slot.start.astimezone(tz)
    text = f"{local:%a} {local.day} {local:%b %H:%M}"
    return f"{slot.resource_name} {text}" if with_doctor else text


def format_date(day: dt.date) -> str:
    return f"{day:%a} {day.day} {day:%b}"
