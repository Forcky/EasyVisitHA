"""Slot parsing and matching (no Home Assistant runtime needed)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from custom_components.easyvisit.const import ANY_DOCTOR
from custom_components.easyvisit.slots import (
    Slot,
    diff_seen,
    format_slot,
    parse_resources,
    qualifying,
    slots_for_watch,
    zone_for,
)

HOBART = ZoneInfo("Australia/Hobart")
UTC = dt.timezone.utc
FIXTURE = Path(__file__).parent / "fixtures" / "resources_sample.json"
MORGAN, LEE, PATEL = 2001, 2002, 2003
# Saturday 27 Sep 2026, 10:00 in Hobart (AEST, before DST starts on 4 Oct).
NOW = dt.datetime(2026, 9, 27, 10, 0, tzinfo=HOBART)


def _resources() -> list[dict]:
    return json.loads(FIXTURE.read_text())["Data"]


def test_parse_localises_to_practice_zone_across_dst():
    doctors, slots = parse_resources(_resources(), UTC)
    assert set(doctors) == {MORGAN, LEE, PATEL}
    assert doctors[MORGAN]["manual_confirm"] is True
    lee = slots_for_watch(slots, LEE)
    assert len(lee) == 5
    # 08:00 on 5 Oct is after DST starts (AEDT, UTC+11), whatever default_tz is.
    assert lee[0].start.astimezone(UTC) == dt.datetime(2026, 10, 4, 21, 0, tzinfo=UTC)
    assert lee[0].api_datetime == "2026-10-05T08:00:00"
    assert slots == sorted(slots)


def test_doctor_with_no_slots_is_still_listed():
    doctors, slots = parse_resources(_resources(), UTC)
    assert doctors[PATEL]["name"] == "Jordan Patel"
    assert slots_for_watch(slots, PATEL) == []


def test_any_doctor_is_the_union():
    _, slots = parse_resources(_resources(), UTC)
    assert slots_for_watch(slots, ANY_DOCTOR) == slots
    assert len(slots) == 5 + 78


def test_unknown_zone_falls_back_to_default():
    assert zone_for("Mars Standard Time", UTC) is UTC
    assert zone_for(None, UTC) is UTC
    assert zone_for("Tasmania Standard Time", UTC) == HOBART


def test_cutoff_is_inclusive_calendar_days():
    _, slots = parse_resources(_resources(), UTC)
    lee = slots_for_watch(slots, LEE)
    # 14 days from 27 Sep = 11 Oct: 5, 7 and 8 Oct qualify, the 15th does not.
    assert [s.api_datetime[:10] for s in qualifying(lee, NOW, 14, HOBART)] == [
        "2026-10-05",
        "2026-10-07",
        "2026-10-08",
    ]
    # 8 days = 5 Oct exactly, the last day included.
    assert len(qualifying(lee, NOW, 8, HOBART)) == 1
    assert qualifying(lee, NOW, 7, HOBART) == []
    morgan = slots_for_watch(slots, MORGAN)
    assert qualifying(morgan, NOW, 14, HOBART) == []
    assert len(qualifying(morgan, NOW, 29, HOBART)) == 1  # 26 Oct 13:45


def test_past_slots_never_qualify():
    past = Slot(NOW - dt.timedelta(minutes=5), MORGAN, "Alex Morgan")
    future = Slot(NOW + dt.timedelta(hours=2), MORGAN, "Alex Morgan")
    assert qualifying([past, future], NOW, 0, HOBART) == [future]


def test_diff_seen_announces_new_and_reopened_slots():
    a = Slot(NOW + dt.timedelta(days=1), MORGAN, "Alex Morgan")
    b = Slot(NOW + dt.timedelta(days=2), MORGAN, "Alex Morgan")
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


def test_format_slot():
    slot = Slot(dt.datetime(2026, 10, 7, 10, 15, tzinfo=HOBART), MORGAN, "Alex Morgan")
    assert format_slot(slot, HOBART) == "Wed 7 Oct 10:15"
    assert format_slot(slot, HOBART, with_doctor=True) == "Alex Morgan Wed 7 Oct 10:15"
