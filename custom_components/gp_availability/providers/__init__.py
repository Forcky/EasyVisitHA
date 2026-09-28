"""Booking providers. To add one, see "Adding a provider" in AGENTS.md."""
from __future__ import annotations

from .base import (
    ApptType,
    Availability,
    Doctor,
    ParsedInput,
    Practice,
    Provider,
    ProviderError,
)
from .easyvisit import EasyVisitProvider
from .hotdoc import HotDocProvider

PROVIDERS: dict[str, type[Provider]] = {
    p.key: p for p in (HotDocProvider, EasyVisitProvider)
}


def detect(text: str) -> tuple[type[Provider], ParsedInput] | None:
    """Which provider a pasted link or ID belongs to (a bare number is EasyVisit)."""
    for provider in PROVIDERS.values():
        if parsed := provider.parse_input(text):
            return provider, parsed
    return None


__all__ = [
    "PROVIDERS",
    "ApptType",
    "Availability",
    "Doctor",
    "ParsedInput",
    "Practice",
    "Provider",
    "ProviderError",
    "detect",
]
