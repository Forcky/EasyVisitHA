"""EasyVisit provider: HTTP client and response parsing."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.gp_availability.providers import ProviderError, base
from custom_components.gp_availability.providers.easyvisit import (
    EasyVisitApiClient,
    parse_resources,
    zone_for,
)
from custom_components.gp_availability.slots import qualifying, slots_for_watch

from .conftest import load

BASE = "https://api.easyvisit.com.au/api/v1/Location/123"
HOBART = ZoneInfo("Australia/Hobart")
UTC = dt.UTC
MORGAN, LEE, PATEL = "2001", "2002", "2003"
NOW = dt.datetime(2026, 9, 27, 10, 0, tzinfo=HOBART)


def _resources() -> list[dict]:
    return load("resources_sample.json")["Data"]


# ---- client -----------------------------------------------------------------


async def test_resources_unwrapped_and_stripped(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(
        f"{BASE}/appointmenttypes/456/resources",
        json={
            "StatusCode": 200,
            "Message": "ok",
            "Data": [{"resourceId": 1, "name": "A", "photoData": "x" * 1000, "bio": "b"}],
        },
    )
    client = EasyVisitApiClient(async_get_clientsession(hass))
    assert await client.get_resources(123, 456) == [{"resourceId": 1, "name": "A"}]


async def test_envelope_error_raises(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(BASE, json={"StatusCode": 404, "Message": "Unable to find locations", "Data": None})
    client = EasyVisitApiClient(async_get_clientsession(hass))
    with pytest.raises(ProviderError, match="404"):
        await client.get_location(123)


async def test_http_error_and_junk_raise(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/appointmenttypes", status=500, text="<html>oops</html>")
    client = EasyVisitApiClient(async_get_clientsession(hass))
    with pytest.raises(ProviderError):
        await client.get_appointment_types(123)


async def test_oversized_response_refused(hass: HomeAssistant, aioclient_mock, monkeypatch):
    monkeypatch.setattr(base, "MAX_BYTES", 100)
    aioclient_mock.get(BASE, json={"StatusCode": 200, "Data": {"name": "x" * 500}})
    client = EasyVisitApiClient(async_get_clientsession(hass))
    with pytest.raises(ProviderError, match="too large"):
        await client.get_location(123)


# ---- parsing ----------------------------------------------------------------


def test_parse_localises_to_practice_zone_across_dst():
    found = parse_resources(_resources(), UTC)
    assert set(found.doctors) == {MORGAN, LEE, PATEL}
    assert found.doctors[MORGAN].manual_confirm is True
    lee = slots_for_watch(found.slots, LEE)
    assert len(lee) == 5
    # 08:00 on 5 Oct is after DST starts (AEDT, UTC+11), whatever default_tz is.
    assert lee[0].start.astimezone(UTC) == dt.datetime(2026, 10, 4, 21, 0, tzinfo=UTC)
    assert lee[0].key == "2002|2026-10-05T08:00:00"
    assert found.doctors[LEE].next_available == lee[0].start
    assert found.slots == sorted(found.slots)


def test_doctor_with_no_slots_is_still_listed():
    found = parse_resources(_resources(), UTC)
    assert found.doctors[PATEL].name == "Jordan Patel"
    assert found.doctors[PATEL].next_available is None
    assert slots_for_watch(found.slots, PATEL) == []


def test_all_slots_are_returned():
    assert len(parse_resources(_resources(), UTC).slots) == 5 + 78


def test_unknown_zone_falls_back_to_default():
    assert zone_for("Mars Standard Time", UTC) is UTC
    assert zone_for(None, UTC) is UTC
    assert zone_for("Tasmania Standard Time", UTC) == HOBART


def test_cutoff_on_recorded_slots():
    found = parse_resources(_resources(), UTC)
    lee = slots_for_watch(found.slots, LEE)
    # 14 days from 27 Sep = 11 Oct: 5, 7 and 8 Oct qualify, the 15th does not.
    assert [s.key[5:15] for s in qualifying(lee, NOW, 14, HOBART)] == [
        "2026-10-05",
        "2026-10-07",
        "2026-10-08",
    ]
    assert len(qualifying(lee, NOW, 8, HOBART)) == 1
    assert qualifying(lee, NOW, 7, HOBART) == []
    morgan = slots_for_watch(found.slots, MORGAN)
    assert qualifying(morgan, NOW, 14, HOBART) == []
    assert len(qualifying(morgan, NOW, 29, HOBART)) == 1  # 26 Oct 13:45
