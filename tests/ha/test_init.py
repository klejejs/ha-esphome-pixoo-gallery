from __future__ import annotations

import io
from datetime import timedelta
from types import SimpleNamespace

import pytest
from aiohttp import FormData
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from PIL import Image
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.esphome_pixoo_gallery.config_flow import _device_entry_ids
from custom_components.esphome_pixoo_gallery.const import DOMAIN

BASE_URL = "http://192.0.2.10:8123"


async def add_display(hass: HomeAssistant, device: dr.DeviceEntry) -> config_entries.ConfigEntry:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device_id": device.id, "base_url": BASE_URL + "/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


@pytest.fixture(autouse=True)
async def setup_deps(hass: HomeAssistant, tmp_path) -> None:
    hass.config.media_dirs = {"local": str(tmp_path / "media")}
    assert await async_setup_component(hass, "http", {})
    lights: list[ServiceCall] = []

    async def light_on(call: ServiceCall) -> None:
        lights.append(call)

    hass.services.async_register("light", "turn_on", light_on)


async def test_flow_finds_the_actions(hass: HomeAssistant, esphome_device) -> None:
    entry = await add_display(hass, esphome_device)
    assert entry.title == "Pixoo 64"
    assert entry.data["action_prefix"] == "pixoo64"
    assert entry.data["base_url"] == BASE_URL
    assert len(entry.data["token"]) >= 30


async def test_flow_rejects_a_device_without_actions(hass: HomeAssistant, esphome_device) -> None:
    hass.services.async_remove("esphome", "pixoo64_show")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device_id": esphome_device.id, "base_url": BASE_URL}
    )
    assert result["errors"] == {"device_id": "no_actions"}


async def test_show_text_sends_the_strip(
    hass: HomeAssistant, hass_client_no_auth, esphome_device, esphome_calls
) -> None:
    entry = await add_display(hass, esphome_device)
    await hass.services.async_call(DOMAIN, "show", {"text": "Sveiki!", "color": [255, 71, 219]}, blocking=True)
    call = esphome_calls[-1]
    assert call.service == "pixoo64_show"
    url = call.data["url"]
    assert url.startswith(f"{BASE_URL}/api/{DOMAIN}/strip/{entry.data['token']}?v=")

    client = await hass_client_no_auth()
    resp = await client.get(url[len(BASE_URL) :])
    assert resp.status == 200
    assert resp.content_type == "image/png"
    assert (await client.get(f"/api/{DOMAIN}/strip/wrong-token")).status == 404

    gallery = entry.runtime_data
    assert gallery.history[0]["source"] == "text:ff47db:Sveiki%21"
    assert gallery.current == gallery.history[0]["key"]
    assert hass.states.get("image.pixoo_64_current_picture") is not None


async def test_forget_and_clear(hass: HomeAssistant, esphome_device, esphome_calls) -> None:
    entry = await add_display(hass, esphome_device)
    await hass.services.async_call(DOMAIN, "show", {"text": "One"}, blocking=True)
    await hass.services.async_call(DOMAIN, "show", {"text": "Two"}, blocking=True)
    gallery = entry.runtime_data
    assert [h["source"].rsplit(":", 1)[1] for h in gallery.history] == ["Two", "One"]

    key = gallery.history[1]["key"]
    await hass.services.async_call(DOMAIN, "forget", {"key": key}, blocking=True)
    assert len(gallery.history) == 1
    assert not gallery.thumb_path(key).exists()

    await hass.services.async_call(DOMAIN, "clear", {}, blocking=True)
    assert esphome_calls[-1].service == "pixoo64_clear"
    assert not gallery.showing


async def test_media_outside_the_media_folder_is_refused(hass: HomeAssistant, esphome_device) -> None:
    await add_display(hass, esphome_device)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "show", {"media": "media-source://media_source/local/../secrets.yaml"}, blocking=True
        )


async def test_upload_and_show_media(hass: HomeAssistant, hass_client, esphome_device, esphome_calls, tmp_path) -> None:
    entry = await add_display(hass, esphome_device)
    client = await hass_client()
    image = io.BytesIO()
    Image.new("RGB", (10, 10), (0, 0, 255)).save(image, format="PNG")
    form = FormData()
    form.add_field("file", image.getvalue(), filename="a.png", content_type="image/png")
    resp = await client.post(f"/api/{DOMAIN}/upload", data=form)
    assert resp.status == 200
    media_id = (await resp.json())["media_content_id"]
    assert media_id.startswith(f"media-source://media_source/local/{DOMAIN}/")

    await hass.services.async_call(DOMAIN, "show", {"media": media_id}, blocking=True)
    gallery = entry.runtime_data
    assert gallery.history[0]["source"] == media_id
    resp = await client.get(f"/api/{DOMAIN}/{entry.entry_id}/history/{gallery.current}")
    assert resp.status == 200


async def test_display_back_online_gets_the_picture_again(
    hass: HomeAssistant, esphome_device, esphome_calls, freezer
) -> None:
    await add_display(hass, esphome_device)
    await hass.services.async_call(DOMAIN, "show", {"text": "Hi"}, blocking=True)
    sent = len(esphome_calls)
    hass.states.async_set("light.pixoo64", "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set("light.pixoo64", "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(esphome_calls) == sent + 1
    assert esphome_calls[-1].service == "pixoo64_show"


def test_device_entry_ids_prefers_single_entry() -> None:
    assert _device_entry_ids(SimpleNamespace(config_entry_id="new", config_entries={"old"})) == ["new"]
    assert _device_entry_ids(SimpleNamespace(config_entry_id=None, config_entries={"old"})) == []
    assert _device_entry_ids(SimpleNamespace(config_entries={"old"})) == ["old"]
