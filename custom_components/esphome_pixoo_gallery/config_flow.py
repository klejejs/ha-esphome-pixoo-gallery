"""Set up a display: pick its ESPHome device and the address it reaches Home Assistant on."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_ACTION_PREFIX, CONF_BASE_URL, CONF_DEVICE_ID, CONF_TOKEN, DOMAIN


def action_prefix(hass: HomeAssistant, device_id: str) -> str | None:
    """The ESPHome action name prefix for a device, if it has the show and clear actions."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for entry_id in _device_entry_ids(device):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != "esphome":
            continue
        name = entry.data.get("device_name")
        if not name:
            continue
        prefix = name.replace("-", "_")
        if hass.services.has_service("esphome", f"{prefix}_show") and hass.services.has_service(
            "esphome", f"{prefix}_clear"
        ):
            return prefix
    return None


def _device_entry_ids(device: dr.DeviceEntry) -> list[str]:
    # Newer Home Assistant gives a device one config_entry_id and deprecates config_entries.
    if hasattr(device, "config_entry_id"):
        return [device.config_entry_id] if device.config_entry_id else []
    return list(device.config_entries)


def default_url(hass: HomeAssistant) -> str:
    try:
        return get_url(hass, allow_external=False, allow_cloud=False, prefer_external=False)
    except NoURLAvailableError:
        return ""


class GalleryConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            base_url = user_input[CONF_BASE_URL].strip().rstrip("/")
            prefix = action_prefix(self.hass, device_id)
            if prefix is None:
                errors[CONF_DEVICE_ID] = "no_actions"
            elif not base_url.startswith(("http://", "https://")):
                errors[CONF_BASE_URL] = "invalid_url"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                device = dr.async_get(self.hass).async_get(device_id)
                title = (device.name_by_user or device.name) if device else prefix
                return self.async_create_entry(
                    title=title or prefix,
                    data={
                        CONF_DEVICE_ID: device_id,
                        CONF_ACTION_PREFIX: prefix,
                        CONF_BASE_URL: base_url,
                        CONF_TOKEN: secrets.token_urlsafe(24),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DeviceSelector(DeviceSelectorConfig(integration="esphome")),
                vol.Required(CONF_BASE_URL, default=default_url(self.hass)): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
