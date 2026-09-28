"""Slot matching, shared by every provider.

Kept free of Home Assistant imports so the logic can be unit-tested with
plain pytest.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable

from .const import ANY_DOCTOR


@dataclass(frozen=True, order=True)
class Slot:
    """One bookable appointment time."""

    start: dt.datetime  # timezone-aware, in the practice's zone; first so slots sort by time
    resource_id: str  # the provider's doctor id
    resource_name: str

    @property
    def key(self) -> str:
        """Stable identity used to remember which slots were already announced."""
        return f"{self.resource_id}|{self.start.replace(tzinfo=None).isoformat()}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "doctor": self.resource_name,
            "resource_id": self.resource_id,
            "start": self.start.isoformat(),
        }


def slots_for_watch(slots: Iterable[Slot], watch_id: str) -> list[Slot]:
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
