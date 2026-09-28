"""Provider-neutral slot matching (no Home Assistant runtime needed)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from custom_components.gp_availability.const import ANY_DOCTOR
from custom_components.gp_availability.slots import (
    Slot,
    diff_seen,
    format_slot,
    qualifying,
    slots_for_watch,
)

HOBART = ZoneInfo("Australia/Hobart")
# Saturday 27 Sep 2026, 10:00 in Hobart (AEST, before DST starts on 4 Oct).
NOW = dt.datetime(2026, 9, 27, 10, 0, tzinfo=HOBART)
MORGAN, LEE = "2001", "2002"


def _slot(days: float, who: str = MORGAN) -> Slot:
    return Slot(NOW + dt.timedelta(days=days), who, who)


def test_any_doctor_is_the_union():
    slots = [_slot(1), _slot(2, LEE)]
    assert slots_for_watch(slots, ANY_DOCTOR) == slots
    assert slots_for_watch(slots, LEE) == [slots[1]]
    assert slots_for_watch(slots, "9999") == []


def test_cutoff_is_inclusive_calendar_days():
    late_on_last_day = Slot(dt.datetime(2026, 10, 11, 23, 30, tzinfo=HOBART), MORGAN, "")
    first_after = Slot(dt.datetime(2026, 10, 12, 0, 0, tzinfo=HOBART), MORGAN, "")
    # 14 days from 27 Sep = 11 Oct, whatever the time of day (and across DST).
    assert qualifying([late_on_last_day, first_after], NOW, 14, HOBART) == [late_on_last_day]
    assert qualifying([late_on_last_day], NOW, 13, HOBART) == []


def test_past_slots_never_qualify():
    past = _slot(-5 / 1440)
    future = _slot(2 / 24)
    assert qualifying([past, future], NOW, 0, HOBART) == [future]


def test_diff_seen_announces_new_and_reopened_slots():
    a, b = _slot(1), _slot(2)
    new, seen = diff_seen([a], set())
    assert new == [a]
    new, seen = diff_seen([a, b], seen)
    assert new == [b]
    new, seen = diff_seen([a, b], seen)
    assert new == []
    # b is booked by someone else, then cancelled again: announce it again.
    new, seen = diff_seen([a], seen)
    assert new == [] and seen == {a.key}
    new, seen = diff_seen([a, b], seen)
    assert new == [b]


def test_key_is_doctor_and_local_time():
    slot = Slot(dt.datetime(2026, 10, 5, 8, 0, tzinfo=HOBART), MORGAN, "Alex Morgan")
    assert slot.key == "2001|2026-10-05T08:00:00"


def test_format_slot():
    slot = Slot(dt.datetime(2026, 10, 7, 10, 15, tzinfo=HOBART), MORGAN, "Alex Morgan")
    assert format_slot(slot, HOBART) == "Wed 7 Oct 10:15"
    assert format_slot(slot, HOBART, with_doctor=True) == "Alex Morgan Wed 7 Oct 10:15"
