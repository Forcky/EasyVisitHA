"""API client against a mocked HTTP layer."""
from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.easyvisit import api as api_mod
from custom_components.easyvisit.api import EasyVisitApiClient, EasyVisitApiError

BASE = "https://api.easyvisit.com.au/api/v1/Location/123"


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
    with pytest.raises(EasyVisitApiError, match="404"):
        await client.get_location(123)


async def test_http_error_and_junk_raise(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/appointmenttypes", status=500, text="<html>oops</html>")
    client = EasyVisitApiClient(async_get_clientsession(hass))
    with pytest.raises(EasyVisitApiError):
        await client.get_appointment_types(123)


async def test_oversized_response_refused(hass: HomeAssistant, aioclient_mock, monkeypatch):
    monkeypatch.setattr(api_mod, "_MAX_BYTES", 100)
    aioclient_mock.get(BASE, json={"StatusCode": 200, "Data": {"name": "x" * 500}})
    client = EasyVisitApiClient(async_get_clientsession(hass))
    with pytest.raises(EasyVisitApiError, match="too large"):
        await client.get_location(123)
