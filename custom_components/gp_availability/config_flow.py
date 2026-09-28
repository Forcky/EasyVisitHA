"""Config and options flow: practice link → appointment type → doctors."""
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

from .const import (
    ANY_DOCTOR,
    CONF_APPT_TYPE_ID,
    CONF_APPT_TYPE_NAME,
    CONF_BOOKING_URL,
    CONF_NOTIFY_TARGETS,
    CONF_PRACTICE_ID,
    CONF_PRACTICE_NAME,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    CONF_TIMEZONE,
    CONF_WATCHES,
    DOMAIN,
    MAX_SCAN_INTERVAL,
)
from .providers import PROVIDERS, ApptType, Doctor, Practice, Provider, ProviderError, detect
from .providers.easyvisit import EXAMPLE_URL as EASYVISIT_EXAMPLE
from .providers.hotdoc import EXAMPLE_URL as HOTDOC_EXAMPLE

_LOGGER = logging.getLogger(__name__)


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


def _doctor_options(doctors: list[Doctor], practice_name: str) -> list[SelectOptionDict]:
    options = [SelectOptionDict(value=ANY_DOCTOR, label=f"Any doctor at {practice_name}")]
    for doc in sorted(doctors, key=lambda d: d.name):
        nxt = doc.next_available.date().isoformat() if doc.next_available else ""
        options.append(
            SelectOptionDict(
                value=doc.id,
                label=f"{doc.name} (next: {nxt})" if nxt else f"{doc.name} (nothing open)",
            )
        )
    return options


def _watch_names(
    selected: list[str], doctors: list[Doctor], previous: dict[str, str]
) -> dict[str, str]:
    names = {d.id: d.name for d in doctors}
    names[ANY_DOCTOR] = "Any doctor"
    return {wid: names.get(wid) or previous.get(wid) or f"Doctor {wid}" for wid in selected}


def _settings_schema(
    hass: HomeAssistant, provider: type[Provider], targets: list[str], interval: int
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
                min=provider.min_scan_interval,
                max=MAX_SCAN_INTERVAL,
                step=1,
                unit_of_measurement="min",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }


class GpAvailabilityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Practice → appointment type → doctors and notifications."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider_cls: type[Provider] | None = None
        self._provider: Provider | None = None
        self._practice: Practice | None = None
        self._appt_hint: str | None = None
        self._doctor_hint: str | None = None
        self._appt_types: list[ApptType] = []
        self._appt_type: ApptType | None = None
        self._doctors: list[Doctor] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (found := detect(user_input["location"])) is None:
                errors["location"] = "unsupported_link"
            else:
                self._provider_cls, parsed = found
                self._provider = self._provider_cls(async_get_clientsession(self.hass))
                self._appt_hint, self._doctor_hint = parsed.appt_type, parsed.doctor
                try:
                    self._practice = await self._provider.get_practice(parsed.practice)
                    self._appt_types = await self._provider.get_appointment_types(
                        self._practice.id
                    )
                except ProviderError as err:
                    _LOGGER.debug("Practice lookup failed: %s", err)
                    errors["location"] = "location_not_found"
                else:
                    if not self._appt_types:
                        errors["location"] = "no_appointment_types"
                    else:
                        return await self.async_step_appointment()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("location"): str}),
            errors=errors,
            description_placeholders={
                "hotdoc_example": HOTDOC_EXAMPLE,
                "easyvisit_example": EASYVISIT_EXAMPLE,
            },
        )

    async def async_step_appointment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._provider and self._practice
        errors: dict[str, str] = {}
        if user_input is not None:
            appt_id = str(user_input[CONF_APPT_TYPE_ID])
            await self.async_set_unique_id(
                f"{self._provider.key}_{self._practice.id}_{appt_id}"
            )
            self._abort_if_unique_id_configured()
            self._appt_type = next(
                (t for t in self._appt_types if t.id == appt_id), ApptType(appt_id, appt_id)
            )
            try:
                self._doctors = await self._provider.get_doctors(self._practice.id, appt_id)
            except ProviderError as err:
                _LOGGER.debug("Doctors lookup failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_doctors()

        ids = [t.id for t in self._appt_types]
        default = self._appt_hint if self._appt_hint in ids else ids[0]
        return self.async_show_form(
            step_id="appointment",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APPT_TYPE_ID, default=default): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=t.id, label=t.name)
                                for t in self._appt_types
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"location": self._practice.name},
        )

    async def async_step_doctors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._provider and self._provider_cls and self._practice and self._appt_type
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = user_input.get(CONF_WATCHES) or []
            if not selected:
                errors[CONF_WATCHES] = "no_doctors"
            elif not valid_notify_targets(user_input.get(CONF_NOTIFY_TARGETS, [])):
                errors[CONF_NOTIFY_TARGETS] = "invalid_notify_target"
            else:
                return self.async_create_entry(
                    title=f"{self._practice.name} · {self._appt_type.name}",
                    data={
                        CONF_PROVIDER: self._provider.key,
                        CONF_PRACTICE_ID: self._practice.id,
                        CONF_PRACTICE_NAME: self._practice.name,
                        CONF_TIMEZONE: self._practice.timezone,
                        CONF_BOOKING_URL: self._provider.booking_url(
                            self._practice, self._appt_type.id
                        ),
                        CONF_APPT_TYPE_ID: self._appt_type.id,
                        CONF_APPT_TYPE_NAME: self._appt_type.name,
                    },
                    options={
                        CONF_WATCHES: _watch_names(selected, self._doctors, {}),
                        CONF_NOTIFY_TARGETS: user_input.get(CONF_NOTIFY_TARGETS, []),
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    },
                )

        preselect = [
            d.id for d in self._doctors if self._doctor_hint in (d.id, d.slug)
        ]
        schema = {
            vol.Required(CONF_WATCHES, default=preselect): SelectSelector(
                SelectSelectorConfig(
                    options=_doctor_options(self._doctors, self._practice.name),
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            **_settings_schema(
                self.hass, self._provider_cls, [], self._provider_cls.default_scan_interval
            ),
        }
        return self.async_show_form(
            step_id="doctors",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "location": self._practice.name,
                "appt_type": self._appt_type.name,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GpAvailabilityOptionsFlow()


class GpAvailabilityOptionsFlow(OptionsFlow):
    """Change watched doctors, notification targets and poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        provider_cls = PROVIDERS[entry.data[CONF_PROVIDER]]
        previous: dict[str, str] = entry.options.get(CONF_WATCHES, {})
        practice_name = entry.data.get(CONF_PRACTICE_NAME, "")
        errors: dict[str, str] = {}
        try:
            doctors = await provider_cls(async_get_clientsession(self.hass)).get_doctors(
                entry.data[CONF_PRACTICE_ID], entry.data[CONF_APPT_TYPE_ID]
            )
        except ProviderError as err:
            _LOGGER.debug("Doctors lookup failed: %s", err)
            doctors = []

        if user_input is not None:
            selected = user_input.get(CONF_WATCHES) or []
            if not selected:
                errors[CONF_WATCHES] = "no_doctors"
            elif not valid_notify_targets(user_input.get(CONF_NOTIFY_TARGETS, [])):
                errors[CONF_NOTIFY_TARGETS] = "invalid_notify_target"
            else:
                return self.async_create_entry(
                    data={
                        CONF_WATCHES: _watch_names(selected, doctors, previous),
                        CONF_NOTIFY_TARGETS: user_input.get(CONF_NOTIFY_TARGETS, []),
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    }
                )

        options = _doctor_options(doctors, practice_name)
        # Keep doctors that are watched but not currently listed selectable.
        listed = {o["value"] for o in options}
        options += [
            SelectOptionDict(value=wid, label=f"{name} (not listed right now)")
            for wid, name in previous.items()
            if wid not in listed
        ]
        schema = {
            vol.Required(CONF_WATCHES, default=list(previous)): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)
            ),
            **_settings_schema(
                self.hass,
                provider_cls,
                entry.options.get(CONF_NOTIFY_TARGETS, []),
                entry.options.get(CONF_SCAN_INTERVAL, provider_cls.default_scan_interval),
            ),
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
