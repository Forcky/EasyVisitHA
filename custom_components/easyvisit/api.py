"""EasyVisit API client.

Availability endpoints are public (no login). Every response is wrapped as
{"StatusCode": int, "Message": str, "Data": ...}. See API.md.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (HomeAssistant; easyvisit)",
}
_TIMEOUT = aiohttp.ClientTimeout(total=30)
# A normal resources response is ~200 KB; refuse anything absurd rather than
# buffering it into memory.
_MAX_BYTES = 10 * 1024 * 1024

# Large, unused fields dropped from resource records straight after parsing
# (photoData alone makes the resources response ~200 KB).
_DROP_FIELDS = ("photoData", "bio")


class EasyVisitApiError(Exception):
    """Raised when the API is unreachable or returns an error."""


class EasyVisitApiClient:
    """Client for the EasyVisit booking API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str) -> Any:
        url = f"{API_BASE}{path}"
        try:
            async with self._session.get(url, headers=_HEADERS, timeout=_TIMEOUT) as resp:
                raw = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    raw += chunk
                    if len(raw) > _MAX_BYTES:
                        raise EasyVisitApiError(f"GET {path}: response too large")
                body = json.loads(raw)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise EasyVisitApiError(f"GET {path} failed: {err}") from err

        if not isinstance(body, dict):
            raise EasyVisitApiError(f"GET {path}: unexpected response")
        status = body.get("StatusCode", resp.status)
        if resp.status != 200 or status != 200:
            raise EasyVisitApiError(
                f"GET {path}: HTTP {resp.status}, {status} {body.get('Message')}"
            )
        return body.get("Data")

    async def get_location(self, location_id: int) -> dict[str, Any]:
        data = await self._get(f"/api/v1/Location/{location_id}")
        if not isinstance(data, dict):
            raise EasyVisitApiError(f"Location {location_id} not found")
        data.pop("photoData", None)
        return data

    async def get_appointment_types(self, location_id: int) -> list[dict[str, Any]]:
        return await self._get(f"/api/v1/Location/{location_id}/appointmenttypes") or []

    async def get_resources(
        self, location_id: int, appt_type_id: int
    ) -> list[dict[str, Any]]:
        """Every doctor offering this appointment type, with all open slots."""
        data = await self._get(
            f"/api/v1/Location/{location_id}/appointmenttypes/{appt_type_id}/resources"
        ) or []
        for res in data:
            for field in _DROP_FIELDS:
                res.pop(field, None)
        return data
