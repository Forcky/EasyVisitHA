"""Config and options flow."""
from __future__ import annotations

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.gp_availability.const import (
    ANY_DOCTOR,
    CONF_APPT_TYPE_ID,
    CONF_BOOKING_URL,
    CONF_NOTIFY_TARGETS,
    CONF_PRACTICE_ID,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    CONF_TIMEZONE,
    CONF_WATCHES,
    DOMAIN,
)
from custom_components.gp_availability.providers import ParsedInput, detect


@pytest.mark.parametrize(
    ("text", "provider", "expected"),
    [
        ("123", "easyvisit", ParsedInput("123")),
        (" 0123 ", "easyvisit", ParsedInput("123")),
        ("https://web.easyvisit.com.au/booking/123/456", "easyvisit", ParsedInput("123", "456")),
        ("web.easyvisit.com.au/booking/123", "easyvisit", ParsedInput("123")),
        (
            "https://www.hotdoc.com.au/medical-centres/kingston-TAS-7050/example-medical-centre/doctors",
            "hotdoc",
            ParsedInput("example-medical-centre"),
        ),
        (
            "https://www.hotdoc.com.au/medical-centres/kingston-TAS-7050/Example-Medical-Centre",
            "hotdoc",
            ParsedInput("example-medical-centre"),
        ),
        (
            "hotdoc.com.au/medical-centres/kingston-TAS-7050/example-medical-centre/doctors/dr-casey-nguyen?x=1",
            "hotdoc",
            ParsedInput("example-medical-centre", doctor="dr-casey-nguyen"),
        ),
        (
            "https://www.hotdoc.com.au/request/consult/start?defaults=practice-example-medical-centre%2Cpractitioner-dr-robin-walsh%2Cwhen-2026",
            "hotdoc",
            ParsedInput("example-medical-centre", doctor="dr-robin-walsh"),
        ),
    ],
)
def test_detect(text, provider, expected):
    found = detect(text)
    assert found is not None
    assert found[0].key == provider
    assert found[1] == expected


@pytest.mark.parametrize(
    "text", ["my-doctor", "https://www.hotdoc.com.au/", "https://healthengine.com.au/x", ""]
)
def test_detect_rejects_junk(text):
    assert detect(text) is None


async def test_full_flow_from_booking_link(hass: HomeAssistant, mock_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": "https://web.easyvisit.com.au/booking/123/457"}
    )
    assert result["step_id"] == "appointment"
    # The appointment type from the link is preselected.
    schema = result["data_schema"].schema
    default = next(k for k in schema if k == CONF_APPT_TYPE_ID).default()
    assert default == "457"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APPT_TYPE_ID: "456"}
    )
    assert result["step_id"] == "doctors"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_WATCHES: ["2001", ANY_DOCTOR],
            CONF_NOTIFY_TARGETS: ["notify.mobile_app_pixel"],
            CONF_SCAN_INTERVAL: 5,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Example Medical Centre · Standard appt."
    assert result["data"][CONF_PROVIDER] == "easyvisit"
    assert result["data"][CONF_PRACTICE_ID] == "123"
    assert result["data"][CONF_APPT_TYPE_ID] == "456"
    assert result["data"][CONF_BOOKING_URL] == "https://web.easyvisit.com.au/booking/123/456"
    assert result["options"][CONF_WATCHES] == {"2001": "Alex Morgan", ANY_DOCTOR: "Any doctor"}
    assert result["result"].unique_id == "easyvisit_123_456"


async def test_needs_at_least_one_doctor(hass: HomeAssistant, mock_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"location": "123"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APPT_TYPE_ID: "456"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WATCHES: [], CONF_SCAN_INTERVAL: 5}
    )
    assert result["errors"] == {CONF_WATCHES: "no_doctors"}


async def test_unsupported_link(hass: HomeAssistant, mock_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": "my-doctor"}
    )
    assert result["errors"] == {"location": "unsupported_link"}


async def test_notify_targets_must_be_notify_services(hass: HomeAssistant, mock_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"location": "123"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APPT_TYPE_ID: "456"}
    )
    for bad in ("homeassistant.stop", "script.unlock_door", "notify.x; y", "mobile_app_pixel"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_WATCHES: ["2001"], CONF_NOTIFY_TARGETS: [bad], CONF_SCAN_INTERVAL: 5},
        )
        assert result["errors"] == {CONF_NOTIFY_TARGETS: "invalid_notify_target"}, bad


async def test_hotdoc_flow_from_doctor_link(hass: HomeAssistant, mock_hotdoc, freezer):
    freezer.move_to("2026-09-28T14:00:00+00:00")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "location": "https://www.hotdoc.com.au/medical-centres/kingston-TAS-7050/"
            "example-medical-centre/doctors/dr-robin-walsh"
        },
    )
    assert result["step_id"] == "appointment"
    options = result["data_schema"].schema[CONF_APPT_TYPE_ID].config["options"]
    # Reason × patient kind, only where a doctor offers it; the deleted
    # new-patient entry for Dr Walsh is ignored.
    assert [o["value"] for o in options] == [
        "501:existing",
        "501:new",
        "502:existing",
        "503:existing",
    ]
    assert options[1]["label"] == "Standard Appointment ( 1 issue ) (new patients)"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APPT_TYPE_ID: "501:existing"}
    )
    assert result["step_id"] == "doctors"
    watches = next(k for k in result["data_schema"].schema if k == CONF_WATCHES)
    assert watches.default() == ["3002"]  # the doctor from the link
    labels = [o["label"] for o in result["data_schema"].schema[watches].config["options"]]
    assert labels == [
        "Any doctor at Example Medical Centre",
        "Dr Casey Nguyen (next: 2026-09-30)",
        "Dr Robin Walsh (next: 2026-10-01)",
        "Dr Taylor Brooks (next: 2026-10-13)",
    ]
    scan = next(k for k in result["data_schema"].schema if k == CONF_SCAN_INTERVAL)
    assert scan.default() == 10

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_WATCHES: ["3002"], CONF_NOTIFY_TARGETS: [], CONF_SCAN_INTERVAL: 10},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROVIDER] == "hotdoc"
    assert result["data"][CONF_PRACTICE_ID] == "999"
    assert result["data"][CONF_TIMEZONE] == "Australia/Hobart"
    assert result["data"][CONF_BOOKING_URL].endswith("/example-medical-centre/doctors")
    assert result["options"][CONF_WATCHES] == {"3002": "Dr Robin Walsh"}
    assert result["result"].unique_id == "hotdoc_999_501:existing"
