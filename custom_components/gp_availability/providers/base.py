"""What every booking provider implements, plus the shared HTTP helper.

No Home Assistant imports: providers only need an aiohttp session, so they
stay easy to test and to try out from a plain Python shell.
"""
from __future__ import annotations

import datetime as dt
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

import aiohttp

from ..slots import Slot

USER_AGENT = "Mozilla/5.0 (HomeAssistant; gp_availability)"
TIMEOUT = aiohttp.ClientTimeout(total=30)
# Refuse anything absurd rather than buffering it into memory.
MAX_BYTES = 10 * 1024 * 1024


class ProviderError(Exception):
    """The booking site is unreachable or returned something unusable."""


@dataclass(frozen=True)
class Practice:
    id: str
    name: str
    timezone: str | None  # IANA name; None = take it from the slots
    booking_url: str


@dataclass(frozen=True)
class ApptType:
    id: str
    name: str


@dataclass
class Doctor:
    id: str
    name: str
    next_available: dt.datetime | None = None
    notes: str = ""
    manual_confirm: bool | None = None  # None = the provider doesn't say
    slug: str | None = None  # how the doctor appears in the provider's links
    url: str | None = None  # the doctor's own booking page, if there is one


@dataclass
class Availability:
    doctors: dict[str, Doctor] = field(default_factory=dict)
    slots: list[Slot] = field(default_factory=list)  # sorted by time


@dataclass(frozen=True)
class ParsedInput:
    """What a pasted link or ID identifies."""

    practice: str
    appt_type: str | None = None  # preselected in the appointment step
    doctor: str | None = None  # id or slug, preselected in the doctors step


async def get_json(
    session: aiohttp.ClientSession, url: str, headers: Mapping[str, str]
) -> Any:
    """GET and parse JSON, raising ProviderError on any failure."""
    try:
        async with session.get(url, headers=dict(headers), timeout=TIMEOUT) as resp:
            raw = bytearray()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                raw += chunk
                if len(raw) > MAX_BYTES:
                    raise ProviderError(f"GET {url}: response too large")
            if resp.status != 200:
                raise ProviderError(f"GET {url}: HTTP {resp.status}")
            return json.loads(raw)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ProviderError(f"GET {url} failed: {err}") from err


class Provider(ABC):
    """One online booking site."""

    key: ClassVar[str]  # stored in the config entry; never change it
    name: ClassVar[str]  # shown as the device manufacturer
    default_scan_interval: ClassVar[int]  # minutes
    min_scan_interval: ClassVar[int]

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    @staticmethod
    @abstractmethod
    def parse_input(text: str) -> ParsedInput | None:
        """Recognise this provider's link or ID, or return None."""

    @abstractmethod
    async def get_practice(self, ref: str) -> Practice:
        """Look up a practice by the ref from parse_input."""

    @abstractmethod
    async def get_appointment_types(self, practice_id: str) -> list[ApptType]:
        """Appointment types a patient can pick, in the site's order."""

    @abstractmethod
    async def get_doctors(self, practice_id: str, appt_type_id: str) -> list[Doctor]:
        """Doctors offering this appointment type, for the config flow."""

    def booking_url(self, practice: Practice, appt_type_id: str) -> str:
        """Where tapping a notification should go."""
        return practice.booking_url

    @abstractmethod
    async def fetch(
        self,
        practice_id: str,
        appt_type_id: str,
        doctor_ids: set[str] | None,
        until: dt.date,
        default_tz: dt.tzinfo,
    ) -> Availability:
        """Open slots up to at least the end of `until` (practice time).

        doctor_ids=None means every doctor. Providers may return more than
        asked for (e.g. all doctors, or slots beyond `until`).
        """
