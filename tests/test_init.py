"""Coordinator, entities and notifications inside a real Home Assistant."""
from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant.core import HomeAssistant

from custom_components.easyvisit.const import (
    CONF_APPT_TYPE_ID,
    CONF_APPT_TYPE_NAME,
    CONF_LOCATION_ID,
    CONF_LOCATION_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_SCAN_INTERVAL,
    CONF_WATCHES,
    DOMAIN,
    EVENT_SLOT_AVAILABLE,
)

MORGAN = "sensor.alex_morgan"
ANY = "example_medical_centre"


def _add_slot(resources: list[dict], resource_id: int, when: str) -> None:
    doctor = next(r for r in resources if r["resourceId"] == resource_id)
    doctor["availableSlotDates"].insert(
        0,
        {
            "date": f"{when[:10]}T00:00:00",
            "slots": [{"resourceId": resource_id, "dateTime": when}],
            "timeZoneId": "Tasmania Standard Time",
        },
    )


def _remove_first_day(resources: list[dict], resource_id: int) -> None:
    doctor = next(r for r in resources if r["resourceId"] == resource_id)
    doctor["availableSlotDates"].pop(0)


@pytest.fixture
async def setup(hass: HomeAssistant, mock_api, freezer):
    await hass.config.async_set_time_zone("Australia/Hobart")
    freezer.move_to("2026-09-27T00:00:00+00:00")  # 10:00 in Hobart
    notify = async_mock_service(hass, "notify", "test_phone")
    events = async_capture_events(hass, EVENT_SLOT_AVAILABLE)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Example Medical Centre · Standard appt.",
        unique_id="123_456",
        data={
            CONF_LOCATION_ID: 123,
            CONF_LOCATION_NAME: "Example Medical Centre",
            CONF_APPT_TYPE_ID: 456,
            CONF_APPT_TYPE_NAME: "Standard appt.",
        },
        options={
            CONF_WATCHES: {"2001": "Alex Morgan", "0": "Any doctor"},
            CONF_NOTIFY_TARGETS: ["notify.test_phone"],
            CONF_SCAN_INTERVAL: 5,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, notify, events, mock_api


async def _poll(hass: HomeAssistant, freezer) -> None:
    freezer.tick(timedelta(minutes=5, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_entities_reflect_availability(hass: HomeAssistant, setup):
    next_available = hass.states.get(f"{MORGAN}_next_available")
    assert next_available.state == "2026-10-26T02:45:00+00:00"  # 13:45 AEDT
    assert next_available.attributes["open_slots"] == 78
    assert next_available.attributes["manual_confirm"] is True
    assert hass.states.get(f"{MORGAN}_slots_before_cutoff").state == "0"
    assert hass.states.get("binary_sensor.alex_morgan_slot_before_cutoff").state == "off"
    assert hass.states.get("switch.alex_morgan_notifications").state == "on"
    assert hass.states.get("number.alex_morgan_cutoff").state == "14"

    # Any doctor defaults to 2 days (to 29 Sep); Dr Lee's first slot is 5 Oct.
    assert hass.states.get(f"number.any_doctor_at_{ANY}_cutoff").state == "2"
    assert hass.states.get(f"sensor.any_doctor_at_{ANY}_slots_before_cutoff").state == "0"
    assert hass.states.get(f"binary_sensor.any_doctor_at_{ANY}_slot_before_cutoff").state == "off"
    assert hass.states.get(f"sensor.any_doctor_at_{ANY}_next_available").attributes["open_slots"] == 83
    assert hass.states.get(f"switch.any_doctor_at_{ANY}_notifications").state == "off"
    assert hass.states.get(f"sensor.{ANY}_last_checked") is not None


async def test_first_poll_is_silent(hass: HomeAssistant, setup):
    _, notify, events, _ = setup
    assert notify == [] and events == []


async def test_new_slot_notifies_once_and_again_after_reopening(
    hass: HomeAssistant, setup, freezer
):
    _, notify, events, resources = setup
    _add_slot(resources, 2001, "2026-09-29T09:00:00")
    await _poll(hass, freezer)

    # Morgan notifies. Any doctor sees it too but is muted: event only.
    assert len(notify) == 1
    call = notify[0].data
    assert call["title"] == "Alex Morgan: 1 new slot by Sun 11 Oct"
    assert call["message"] == "Tue 29 Sep 09:00"
    assert call["data"]["clickAction"] == "https://web.easyvisit.com.au/booking/123/456"
    assert {e.data["watch_id"] for e in events} == {2001, 0}
    assert hass.states.get(f"{MORGAN}_slots_before_cutoff").state == "1"

    await _poll(hass, freezer)
    assert len(notify) == 1  # nothing new

    _remove_first_day(resources, 2001)  # someone booked it
    await _poll(hass, freezer)
    assert len(notify) == 1
    assert hass.states.get(f"{MORGAN}_slots_before_cutoff").state == "0"

    _add_slot(resources, 2001, "2026-09-29T09:00:00")  # cancelled again
    await _poll(hass, freezer)
    assert len(notify) == 2


async def test_switch_mutes_but_event_still_fires(hass: HomeAssistant, setup, freezer):
    _, notify, events, resources = setup
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.alex_morgan_notifications"}, blocking=True
    )
    _add_slot(resources, 2001, "2026-10-01T09:00:00")
    await _poll(hass, freezer)
    assert notify == []
    assert any(e.data["watch_id"] == 2001 for e in events)


async def test_raising_cutoff_announces_slots_now_inside(hass: HomeAssistant, setup, freezer):
    _, notify, _, _ = setup
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.alex_morgan_cutoff", "value": 29},
        blocking=True,
    )
    await _poll(hass, freezer)
    assert len(notify) == 1
    assert notify[0].data["message"] == "Mon 26 Oct 13:45"


async def test_test_button_sends_current_slots(hass: HomeAssistant, setup):
    _, notify, _, _ = setup
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.any_doctor_at_{ANY}_cutoff", "value": 14},
        blocking=True,
    )
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": f"button.any_doctor_at_{ANY}_send_test_notification"},
        blocking=True,
    )
    assert len(notify) == 1
    assert notify[0].data["title"].startswith("[Test] Any doctor: 3 new slots")
    assert notify[0].data["message"].splitlines()[0] == "Sam Lee Mon 5 Oct 08:00"


async def test_settings_survive_reload(hass: HomeAssistant, setup):
    entry, _, _, _ = setup
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.alex_morgan_cutoff", "value": 21},
        blocking=True,
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.alex_morgan_cutoff").state == "21"


async def test_options_flow_removes_unwatched_doctor(hass: HomeAssistant, setup):
    from homeassistant.helpers import device_registry as dr

    entry, _, _, _ = setup
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_WATCHES: ["2001"], CONF_NOTIFY_TARGETS: ["notify.test_phone"], CONF_SCAN_INTERVAL: 10},
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_WATCHES] == {"2001": "Alex Morgan"}
    assert entry.runtime_data.update_interval == timedelta(minutes=10)

    names = {d.name for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)}
    assert names == {"Example Medical Centre", "Alex Morgan"}
    assert hass.states.get(f"{MORGAN}_next_available") is not None


async def test_non_notify_target_is_never_called(hass: HomeAssistant, setup):
    """Even if options were edited by hand, only notify.* services are called."""
    from pytest_homeassistant_custom_component.common import async_mock_service

    entry, notify, _, _ = setup
    stop = async_mock_service(hass, "homeassistant", "restart")
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_NOTIFY_TARGETS: ["homeassistant.restart"]}
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.alex_morgan_send_test_notification"},
        blocking=True,
    )
    assert stop == []
