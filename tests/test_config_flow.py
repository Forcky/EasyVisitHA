"""Config and options flow."""
from __future__ import annotations

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.easyvisit.config_flow import parse_location_input
from custom_components.easyvisit.const import (
    CONF_APPT_TYPE_ID,
    CONF_LOCATION_ID,
    CONF_NOTIFY_TARGETS,
    CONF_SCAN_INTERVAL,
    CONF_WATCHES,
    DOMAIN,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("123", (123, None)),
        (" 123 ", (123, None)),
        ("https://web.easyvisit.com.au/booking/123/456", (123, 456)),
        ("web.easyvisit.com.au/booking/123", (123, None)),
    ],
)
def test_parse_location_input(text, expected):
    assert parse_location_input(text) == expected


def test_parse_location_input_rejects_junk():
    with pytest.raises(ValueError):
        parse_location_input("my-doctor")


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
            CONF_WATCHES: ["2001", "0"],
            CONF_NOTIFY_TARGETS: ["notify.mobile_app_pixel"],
            CONF_SCAN_INTERVAL: 5,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Example Medical Centre · Standard appt."
    assert result["data"][CONF_LOCATION_ID] == 123
    assert result["data"][CONF_APPT_TYPE_ID] == 456
    assert result["options"][CONF_WATCHES] == {"2001": "Alex Morgan", "0": "Any doctor"}


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


async def test_invalid_location_input(hass: HomeAssistant, mock_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": "my-doctor"}
    )
    assert result["errors"] == {"location": "invalid_location"}


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
