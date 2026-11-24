"""WebSocket commands the card uses."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATED
from .gallery import Gallery
from .http import galleries


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_displays)
    websocket_api.async_register_command(hass, ws_subscribe)


def _find(hass: HomeAssistant, entry_id: str) -> Gallery | None:
    return next((g for g in galleries(hass) if g.entry.entry_id == entry_id), None)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/displays"})
@callback
def ws_displays(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """List the displays, with the image entity that shows each one's current picture."""
    registry = er.async_get(hass)
    result = []
    for gallery in galleries(hass):
        entities = er.async_entries_for_config_entry(registry, gallery.entry.entry_id)
        image = next((e.entity_id for e in entities if e.domain == "image"), None)
        result.append({"entry_id": gallery.entry.entry_id, "title": gallery.entry.title, "image_entity": image})
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe", vol.Required("entry_id"): str})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Send the history and the current key now and after every change."""
    entry_id = msg["entry_id"]
    if _find(hass, entry_id) is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "No such display")
        return

    @callback
    def send() -> None:
        gallery = _find(hass, entry_id)
        if gallery is None:
            return
        connection.send_message(
            websocket_api.event_message(msg["id"], {"history": gallery.history, "current": gallery.current})
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL_UPDATED.format(entry_id=entry_id), send)
    connection.send_result(msg["id"])
    send()
