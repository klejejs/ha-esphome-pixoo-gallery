"""Actions: show, forget and clear."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_COLOR,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_KEY,
    ATTR_MEDIA,
    ATTR_TEXT,
    ATTR_URL,
    DEFAULT_COLOR,
    DOMAIN,
)
from .gallery import Gallery
from .http import galleries

COLOR = vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple))


def _media_id(value: object) -> str:
    """Take a media selector's value or a plain media-source id."""
    if isinstance(value, dict):
        value = value.get("media_content_id")
    return cv.string(value)


BASE = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
SHOW_SCHEMA = vol.All(
    vol.Schema(
        {
            **BASE,
            vol.Exclusive(ATTR_URL, "source"): cv.url,
            vol.Exclusive(ATTR_MEDIA, "source"): _media_id,
            vol.Exclusive(ATTR_TEXT, "source"): cv.string,
            vol.Optional(ATTR_COLOR, default=list(DEFAULT_COLOR)): COLOR,
        }
    ),
    cv.has_at_least_one_key(ATTR_URL, ATTR_MEDIA, ATTR_TEXT),
)
FORGET_SCHEMA = vol.Schema({**BASE, vol.Required(ATTR_KEY): vol.Match(r"^[0-9a-f]{12}$")})
CLEAR_SCHEMA = vol.Schema(BASE)


def _gallery(hass: HomeAssistant, call: ServiceCall) -> Gallery:
    found = galleries(hass)
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        found = [g for g in found if g.entry.entry_id == entry_id]
    if not found:
        raise ServiceValidationError("No Pixoo display is set up with that ID")
    if len(found) > 1:
        raise ServiceValidationError("There is more than one Pixoo display: pick one")
    return found[0]


@callback
def async_register(hass: HomeAssistant) -> None:
    async def show(call: ServiceCall) -> None:
        gallery = _gallery(hass, call)
        if ATTR_TEXT in call.data:
            await gallery.async_show_text(call.data[ATTR_TEXT], call.data[ATTR_COLOR])
        elif ATTR_MEDIA in call.data:
            await gallery.async_show_media(call.data[ATTR_MEDIA])
        else:
            await gallery.async_show_url(call.data[ATTR_URL])

    async def forget(call: ServiceCall) -> None:
        await _gallery(hass, call).async_forget(call.data[ATTR_KEY])

    async def clear(call: ServiceCall) -> None:
        await _gallery(hass, call).async_clear()

    hass.services.async_register(DOMAIN, "show", show, schema=SHOW_SCHEMA)
    hass.services.async_register(DOMAIN, "forget", forget, schema=FORGET_SCHEMA)
    hass.services.async_register(DOMAIN, "clear", clear, schema=CLEAR_SCHEMA)
