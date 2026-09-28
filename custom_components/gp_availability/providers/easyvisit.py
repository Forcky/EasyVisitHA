"""EasyVisit (web.easyvisit.com.au), used by IPN / Sonic practices.

Availability endpoints are public (no login). Every response is wrapped as
{"StatusCode": int, "Message": str, "Data": ...}. See API.md.
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from ..slots import Slot
from .base import (
    USER_AGENT,
    ApptType,
    Availability,
    Doctor,
    ParsedInput,
    Practice,
    Provider,
    ProviderError,
    get_json,
)

API_BASE = "https://api.easyvisit.com.au"
BOOKING_URL = "https://web.easyvisit.com.au/booking/{location_id}/{appt_type_id}"
EXAMPLE_URL = "https://web.easyvisit.com.au/booking/123/456"

_HEADERS = {"Accept": "application/json", "User-Agent": USER_AGENT}
# Large, unused fields dropped from resource records straight after parsing
# (photoData alone makes the resources response ~200 KB).
_DROP_FIELDS = ("photoData", "bio")
_BOOKING_RE = re.compile(r"easyvisit\.com\.au/booking/(\d+)(?:/(\d+))?")

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


class EasyVisitApiClient:
    """Client for the EasyVisit booking API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str) -> Any:
        body = await get_json(self._session, f"{API_BASE}{path}", _HEADERS)
        if not isinstance(body, dict):
            raise ProviderError(f"GET {path}: unexpected response")
        status = body.get("StatusCode", 200)
        if status != 200:
            raise ProviderError(f"GET {path}: {status} {body.get('Message')}")
        return body.get("Data")

    async def get_location(self, location_id: int) -> dict[str, Any]:
        data = await self._get(f"/api/v1/Location/{location_id}")
        if not isinstance(data, dict):
            raise ProviderError(f"Location {location_id} not found")
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


def zone_for(windows_name: str | None, default: dt.tzinfo) -> dt.tzinfo:
    """Map an EasyVisit (Windows) time zone name to a tzinfo."""
    iana = _WINDOWS_TZ.get(windows_name or "")
    return ZoneInfo(iana) if iana else default


def parse_resources(
    resources: Iterable[dict[str, Any]], default_tz: dt.tzinfo
) -> Availability:
    """Doctors (keyed by resourceId as a string) and all their slots, sorted."""
    result = Availability()
    for res in resources:
        rid = str(res["resourceId"])
        name = (res.get("name") or f"Resource {rid}").strip()
        doctor = Doctor(
            id=rid,
            name=name,
            notes=(res.get("notesForPatients") or "").strip(),
            manual_confirm=bool(res.get("manualConfirm")),
        )
        result.doctors[rid] = doctor
        for day in res.get("availableSlotDates") or []:
            tz = zone_for(day.get("timeZoneId"), default_tz)
            for raw in day.get("slots") or []:
                start = dt.datetime.fromisoformat(raw["dateTime"])
                if start.tzinfo is None:
                    start = start.replace(tzinfo=tz)
                result.slots.append(Slot(start, str(raw.get("resourceId", rid)), name))
    result.slots.sort()
    # Every open slot comes back (about 6 weeks), so the first is the next.
    for slot in result.slots:
        doctor = result.doctors.get(slot.resource_id)
        if doctor and doctor.next_available is None:
            doctor.next_available = slot.start
    return result


class EasyVisitProvider(Provider):
    key = "easyvisit"
    name = "EasyVisit"
    default_scan_interval = 5
    min_scan_interval = 2

    def __init__(self, session: aiohttp.ClientSession) -> None:
        super().__init__(session)
        self.client = EasyVisitApiClient(session)

    @staticmethod
    def parse_input(text: str) -> ParsedInput | None:
        """Accept '123' or a booking URL like '.../booking/123/456'."""
        text = text.strip()
        if text.isdigit():
            return ParsedInput(practice=str(int(text)))
        if match := _BOOKING_RE.search(text):
            return ParsedInput(practice=match.group(1), appt_type=match.group(2))
        return None

    async def get_practice(self, ref: str) -> Practice:
        location = await self.client.get_location(int(ref))
        return Practice(
            id=ref,
            name=(location.get("name") or f"Location {ref}").strip(),
            timezone=None,  # each day's slots carry their own zone
            booking_url=f"https://web.easyvisit.com.au/booking/{ref}",
        )

    async def get_appointment_types(self, practice_id: str) -> list[ApptType]:
        types = await self.client.get_appointment_types(int(practice_id))
        return [ApptType(str(t["apptTypeID"]), t["name"].strip()) for t in types]

    async def get_doctors(self, practice_id: str, appt_type_id: str) -> list[Doctor]:
        # Labels only need the date, so the zone fallback doesn't matter here.
        found = await self.fetch(practice_id, appt_type_id, None, dt.date.today(), dt.UTC)
        return list(found.doctors.values())

    async def fetch(
        self,
        practice_id: str,
        appt_type_id: str,
        doctor_ids: set[str] | None,
        until: dt.date,
        default_tz: dt.tzinfo,
    ) -> Availability:
        # One call returns every doctor and every open slot, whatever `until` is.
        resources = await self.client.get_resources(int(practice_id), int(appt_type_id))
        return parse_resources(resources, default_tz)

    def booking_url(self, practice: Practice, appt_type_id: str) -> str:
        return BOOKING_URL.format(location_id=practice.id, appt_type_id=appt_type_id)
