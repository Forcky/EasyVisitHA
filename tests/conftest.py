"""Shared fixtures."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "resources_sample.json"

LOCATION = {"locationID": 123, "name": "Example Medical Centre"}
APPT_TYPES = [
    {"apptTypeID": 456, "name": "Standard appt."},
    {"apptTypeID": 457, "name": "Long appt."},
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def resources() -> list[dict]:
    """Mutable copy of the recorded resources response; edit it between polls."""
    return copy.deepcopy(json.loads(FIXTURE.read_text())["Data"])


@pytest.fixture
def mock_api(resources):
    """Patch the API client so nothing reaches the network."""

    async def get_resources(self, location_id, appt_type_id):
        return copy.deepcopy(resources)

    async def get_location(self, location_id):
        return dict(LOCATION)

    async def get_appointment_types(self, location_id):
        return list(APPT_TYPES)

    base = "custom_components.easyvisit.api.EasyVisitApiClient"
    with (
        patch(f"{base}.get_resources", get_resources),
        patch(f"{base}.get_location", get_location),
        patch(f"{base}.get_appointment_types", get_appointment_types),
    ):
        yield resources
