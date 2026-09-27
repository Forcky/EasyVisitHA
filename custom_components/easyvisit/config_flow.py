"""Config and options flow for EasyVisit."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import EasyVisitApiClient, EasyVisitApiError
from .const import (
    ANY_DOCTOR,
    CONF_APPT_TYPE_ID,
    CONF_APPT_TYPE_NAME,
    CONF_LOCATION_ID,
    CONF_LOCATION_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_SCAN_INTERVAL,
    CONF_WATCHES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EXAMPLE_BOOKING_URL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_BOOKING_RE = re.compile(r"booking/(\d+)(?:/(\d+))?")
_ANY = str(ANY_DOCTOR)


def parse_location_input(text: str) -> tuple[int, int | None]:
    """Accept '123' or a booking URL like '.../booking/123/456'."""
    text = text.strip()
    if text.isdigit():
        return int(text), None
    if match := _BOOKING_RE.search(text):
        appt = match.group(2)
        return int(match.group(1)), int(appt) if appt else None
    raise ValueError(text)


def valid_notify_targets(targets: list[str]) -> bool:
    """Only notify.<service> is allowed: the targets are called as services, so
    anything else would let the options form trigger arbitrary actions."""
    return all(re.fullmatch(r"notify\.[a-z0-9_]+", t) for t in targets)


def _notify_options(hass: HomeAssistant, current: list[str]) -> list[str]:
    services = [
        f"notify.{name}"
        for name in sorted(hass.services.async_services_for_domain("notify"))
        if name != "send_message"  # entity-based; needs an entity_id
    ]
    return services + [t for t in current if t not in services]


def _doctor_options(resources: list[dict[str, Any]], location_name: str) -> list[SelectOptionDict]:
    options = [SelectOptionDict(value=_ANY, label=f"Any doctor at {location_name}")]
    for res in sorted(resources, key=lambda r: r.get("name") or ""):
        nxt = (res.get("nextAvailableSlot") or "")[:10]
        label = res.get("name") or f"Resource {res['resourceId']}"
        options.append(
            SelectOptionDict(
                value=str(res["resourceId"]),
                label=f"{label} (next: {nxt})" if nxt else f"{label} (nothing open)",
            )
        )
    return options


def _watch_names(
    selected: list[str], resources: list[dict[str, Any]], previous: dict[str, str]
) -> dict[str, str]:
    names = {str(r["resourceId"]): (r.get("name") or "").strip() for r in resources}
    names[_ANY] = "Any doctor"
    return {rid: names.get(rid) or previous.get(rid) or f"Resource {rid}" for rid in selected}


def _settings_schema(
    hass: HomeAssistant, targets: list[str], interval: int
) -> dict[Any, Any]:
    return {
        vol.Optional(CONF_NOTIFY_TARGETS, default=targets): SelectSelector(
            SelectSelectorConfig(
                options=_notify_options(hass, targets),
                multiple=True,
                custom_value=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_SCAN_INTERVAL, default=interval): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=1,
                unit_of_measurement="min",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }


class EasyVisitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Practice → appointment type → doctors and notifications."""

    VERSION = 1

    def __init__(self) -> None:
        self._location_id = 0
        self._location_name = ""
        self._appt_hint: int | None = None
        self._appt_types: list[dict[str, Any]] = []
        self._appt_type_id = 0
        self._appt_type_name = ""
        self._resources: list[dict[str, Any]] = []

    def _client(self) -> EasyVisitApiClient:
        return EasyVisitApiClient(async_get_clientsession(self.hass))

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._location_id, self._appt_hint = parse_location_input(user_input["location"])
            except ValueError:
                errors["location"] = "invalid_location"
            else:
                try:
                    client = self._client()
                    location = await client.get_location(self._location_id)
                    self._appt_types = await client.get_appointment_types(self._location_id)
                except EasyVisitApiError as err:
                    _LOGGER.debug("Location lookup failed: %s", err)
                    errors["location"] = "location_not_found"
                else:
                    self._location_name = location.get("name") or f"Location {self._location_id}"
                    if not self._appt_types:
                        errors["location"] = "no_appointment_types"
                    else:
                        return await self.async_step_appointment()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("location"): str}
            ),
            errors=errors,
            description_placeholders={"example": EXAMPLE_BOOKING_URL},
        )

    async def async_step_appointment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._appt_type_id = int(user_input[CONF_APPT_TYPE_ID])
            await self.async_set_unique_id(f"{self._location_id}_{self._appt_type_id}")
            self._abort_if_unique_id_configured()
            self._appt_type_name = next(
                (t["name"] for t in self._appt_types if t["apptTypeID"] == self._appt_type_id),
                str(self._appt_type_id),
            ).strip()
            try:
                self._resources = await self._client().get_resources(
                    self._location_id, self._appt_type_id
                )
            except EasyVisitApiError as err:
                _LOGGER.debug("Resources lookup failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_doctors()

        ids = [t["apptTypeID"] for t in self._appt_types]
        default = self._appt_hint if self._appt_hint in ids else ids[0]
        return self.async_show_form(
            step_id="appointment",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APPT_TYPE_ID, default=str(default)): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=str(t["apptTypeID"]), label=t["name"].strip())
                                for t in self._appt_types
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"location": self._location_name},
        )

    async def async_step_doctors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = user_input.get(CONF_WATCHES) or []
            if not selected:
                errors[CONF_WATCHES] = "no_doctors"
            elif not valid_notify_targets(user_input.get(CONF_NOTIFY_TARGETS, [])):
                errors[CONF_NOTIFY_TARGETS] = "invalid_notify_target"
            else:
                return self.async_create_entry(
                    title=f"{self._location_name} · {self._appt_type_name}",
                    data={
                        CONF_LOCATION_ID: self._location_id,
                        CONF_LOCATION_NAME: self._location_name,
                        CONF_APPT_TYPE_ID: self._appt_type_id,
                        CONF_APPT_TYPE_NAME: self._appt_type_name,
                    },
                    options={
                        CONF_WATCHES: _watch_names(selected, self._resources, {}),
                        CONF_NOTIFY_TARGETS: user_input.get(CONF_NOTIFY_TARGETS, []),
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    },
                )

        schema = {
            vol.Required(CONF_WATCHES): SelectSelector(
                SelectSelectorConfig(
                    options=_doctor_options(self._resources, self._location_name),
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            **_settings_schema(self.hass, [], DEFAULT_SCAN_INTERVAL),
        }
        return self.async_show_form(
            step_id="doctors",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "location": self._location_name,
                "appt_type": self._appt_type_name,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EasyVisitOptionsFlow()


class EasyVisitOptionsFlow(OptionsFlow):
    """Change watched doctors, notification targets and poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        previous: dict[str, str] = entry.options.get(CONF_WATCHES, {})
        location_name = entry.data.get(CONF_LOCATION_NAME, "")
        errors: dict[str, str] = {}
        try:
            resources = await EasyVisitApiClient(
                async_get_clientsession(self.hass)
            ).get_resources(entry.data[CONF_LOCATION_ID], entry.data[CONF_APPT_TYPE_ID])
        except EasyVisitApiError as err:
            _LOGGER.debug("Resources lookup failed: %s", err)
            resources = []

        if user_input is not None:
            selected = user_input.get(CONF_WATCHES) or []
            if not selected:
                errors[CONF_WATCHES] = "no_doctors"
            elif not valid_notify_targets(user_input.get(CONF_NOTIFY_TARGETS, [])):
                errors[CONF_NOTIFY_TARGETS] = "invalid_notify_target"
            else:
                return self.async_create_entry(
                    data={
                        CONF_WATCHES: _watch_names(selected, resources, previous),
                        CONF_NOTIFY_TARGETS: user_input.get(CONF_NOTIFY_TARGETS, []),
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    }
                )

        options = _doctor_options(resources, location_name)
        # Keep doctors that are watched but not currently listed selectable.
        listed = {o["value"] for o in options}
        options += [
            SelectOptionDict(value=rid, label=f"{name} (not listed right now)")
            for rid, name in previous.items()
            if rid not in listed
        ]
        schema = {
            vol.Required(CONF_WATCHES, default=list(previous)): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)
            ),
            **_settings_schema(
                self.hass,
                entry.options.get(CONF_NOTIFY_TARGETS, []),
                entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
