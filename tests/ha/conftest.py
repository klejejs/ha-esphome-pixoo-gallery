"""Fixtures for tests against a real Home Assistant core."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def esphome_calls(hass: HomeAssistant) -> list[ServiceCall]:
    """Stand-ins for the actions the ESPHome package adds."""
    calls: list[ServiceCall] = []

    async def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("esphome", "pixoo64_show", record)
    hass.services.async_register("esphome", "pixoo64_clear", record)
    return calls


@pytest.fixture
def esphome_device(hass: HomeAssistant, esphome_calls) -> dr.DeviceEntry:
    entry = MockConfigEntry(domain="esphome", data={"device_name": "pixoo64", "host": "pixoo64.local"})
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        name="Pixoo 64",
    )
    er.async_get(hass).async_get_or_create(
        "light", "esphome", "pixoo64-light", device_id=device.id, config_entry=entry, suggested_object_id="pixoo64"
    )
    return device
