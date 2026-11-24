"""Show pictures, GIFs and scrolling text on a Pixoo 64 running ESPHome."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import http, services, websocket
from .const import CARD_URL, DOMAIN
from .gallery import Gallery

PLATFORMS = [Platform.IMAGE]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type GalleryConfigEntry = ConfigEntry[Gallery]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    card = Path(__file__).parent / "frontend" / "esphome-pixoo-gallery-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), True)])
    if "frontend" in hass.config.components:
        version = (await hass.async_add_executor_job(card.stat)).st_mtime_ns
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    http.async_register(hass)
    websocket.async_register(hass)
    services.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GalleryConfigEntry) -> bool:
    gallery = Gallery(hass, entry)
    await gallery.async_load()
    entry.runtime_data = gallery
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GalleryConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.async_unload()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: GalleryConfigEntry) -> None:
    await Gallery(hass, entry).async_remove()
