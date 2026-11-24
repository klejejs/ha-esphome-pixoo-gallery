"""One Pixoo display: what it shows, its history, and how to reach it."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import convert
from .const import (
    CONF_ACTION_PREFIX,
    CONF_BASE_URL,
    CONF_DEVICE_ID,
    CONF_TOKEN,
    DOMAIN,
    HISTORY_MAX,
    MAX_BYTES,
    SIGNAL_UPDATED,
    STRIP_URL,
)

_LOGGER = logging.getLogger(__name__)

MEDIA_PREFIX = "media-source://media_source/"
STORE_VERSION = 1
RESEND_DELAY_S = 3


class Gallery:
    """State and actions for one display."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.dir = Path(hass.config.path(DOMAIN, entry.entry_id))
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._lock = asyncio.Lock()
        self._unsubs: list[Callable[[], None]] = []
        self._resend_cancel: Callable[[], None] | None = None
        self.history: list[dict[str, Any]] = []
        self.current: str | None = None
        self.showing = False
        self.strip: bytes | None = None
        self.preview: bytes | None = None
        self.updated: datetime | None = None

    @property
    def token(self) -> str:
        return self.entry.data[CONF_TOKEN]

    @property
    def device_id(self) -> str:
        return self.entry.data[CONF_DEVICE_ID]

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.history = data.get("history", [])
        self.current = data.get("current")
        self.showing = data.get("showing", False)
        self.strip, self.preview = await self.hass.async_add_executor_job(self._read_current)
        if self.preview is not None:
            self.updated = dt_util.utcnow()
        self._watch_device()

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._resend_cancel:
            self._resend_cancel()
            self._resend_cancel = None

    async def async_remove(self) -> None:
        await self._store.async_remove()
        await self.hass.async_add_executor_job(shutil.rmtree, self.dir, True)

    def thumb_path(self, key: str) -> Path:
        return self.dir / "history" / f"{key}.gif"

    # Showing

    async def async_show_source(self, source: str) -> None:
        """Show a history source again: a link, a media item or a text."""
        if source.startswith("text:"):
            text, rgb = convert.parse_text_source(source)
            await self.async_show_text(text, rgb)
        elif source.startswith(MEDIA_PREFIX):
            await self.async_show_media(source)
        else:
            await self.async_show_url(source)

    async def async_show_url(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            raise HomeAssistantError("A link has to start with http:// or https://")
        data = await self._download(url)
        result = await self._convert_image(data)
        await self._show(url, result)

    async def async_show_media(self, media_id: str) -> None:
        path = self._media_path(media_id)
        data = await self.hass.async_add_executor_job(_read_limited, path)
        result = await self._convert_image(data)
        await self._show(media_id, result)

    async def async_show_text(self, text: str, rgb: tuple[int, int, int]) -> None:
        text = convert.clean_text(text)
        if not text:
            raise HomeAssistantError("The text is empty")
        result = await self.hass.async_add_executor_job(convert.convert_text, text, rgb)
        await self._show(convert.text_source(text, rgb), result)

    async def async_forget(self, key: str) -> None:
        async with self._lock:
            self.history = [h for h in self.history if h["key"] != key]
            await self.hass.async_add_executor_job(_remove, self.thumb_path(key))
            self._save()
        self._notify()

    async def async_clear(self) -> None:
        await self.hass.services.async_call(
            "esphome", f"{self.entry.data[CONF_ACTION_PREFIX]}_clear", {}, blocking=True
        )
        self.showing = False
        self.current = None
        self._save()
        self._notify()

    async def _show(self, source: str, result: convert.Converted) -> None:
        key = convert.history_key(source)
        async with self._lock:
            await self.hass.async_add_executor_job(self._write, key, result)
            self.strip, self.preview = result.strip, result.preview
            self.updated = dt_util.utcnow()
            self.history = [h for h in self.history if h["key"] != key]
            self.history.insert(0, {"key": key, "source": source, "frames": result.frames, "time": int(time.time())})
            for dropped in self.history[HISTORY_MAX:]:
                await self.hass.async_add_executor_job(_remove, self.thumb_path(dropped["key"]))
            del self.history[HISTORY_MAX:]
            self.current = key
            self.showing = True
            self._save()
        self._notify()
        await self._turn_on_light()
        await self._send(result.delay_ms)

    async def _send(self, delay_ms: int) -> None:
        base = self.entry.data[CONF_BASE_URL].rstrip("/")
        url = f"{base}{STRIP_URL.format(token=self.token)}?v={int(time.time() * 1000)}"
        await self.hass.services.async_call(
            "esphome",
            f"{self.entry.data[CONF_ACTION_PREFIX]}_show",
            {"url": url, "delay_ms": delay_ms},
            blocking=True,
        )

    async def _turn_on_light(self) -> None:
        light = next(
            (e.entity_id for e in self._device_entities() if e.domain == "light"),
            None,
        )
        if light:
            await self.hass.services.async_call("light", "turn_on", {"entity_id": light}, blocking=True)

    # The display forgets the picture when it loses power, so send it again when it comes back.

    def _device_entities(self) -> list[er.RegistryEntry]:
        registry = er.async_get(self.hass)
        return [e for e in er.async_entries_for_device(registry, self.device_id) if e.platform == "esphome"]

    @callback
    def _watch_device(self) -> None:
        entity_ids = [e.entity_id for e in self._device_entities()]
        if entity_ids:
            self._unsubs.append(async_track_state_change_event(self.hass, entity_ids, self._on_device_state))

    @callback
    def _on_device_state(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if not (old and new and old.state == STATE_UNAVAILABLE and new.state != STATE_UNAVAILABLE):
            return
        if not self.showing or self.strip is None or self._resend_cancel:
            return
        self._resend_cancel = async_call_later(self.hass, RESEND_DELAY_S, self._resend)

    async def _resend(self, _now: datetime) -> None:
        self._resend_cancel = None
        _LOGGER.debug("Display is back, sending the picture again")
        try:
            # The strip carries its own timing, so the delay here only matters until it loads.
            await self._send(0)
        except HomeAssistantError as err:
            _LOGGER.warning("Could not send the picture to the display again: %s", err)

    # Sources

    async def _download(self, url: str) -> bytes:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, timeout=20, headers={"User-Agent": "esphome-pixoo-gallery"}) as resp:
                resp.raise_for_status()
                data = bytearray()
                async for chunk in resp.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise HomeAssistantError("The file is larger than 20 MB")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Could not download {url}: {err}") from err
        return bytes(data)

    async def _convert_image(self, data: bytes) -> convert.Converted:
        try:
            return await self.hass.async_add_executor_job(convert.convert_image, data)
        except (OSError, ValueError) as err:
            raise HomeAssistantError(f"Not a picture this can read: {err}") from err

    def _media_path(self, media_id: str) -> Path:
        if not media_id.startswith(MEDIA_PREFIX):
            raise HomeAssistantError(f"Not a local media item: {media_id}")
        source_dir, _, relative = media_id[len(MEDIA_PREFIX) :].partition("/")
        root = self.hass.config.media_dirs.get(source_dir)
        if root is None or not relative:
            raise HomeAssistantError(f"Not a local media item: {media_id}")
        root_path = os.path.realpath(root)
        path = os.path.realpath(os.path.join(root_path, relative))
        if not path.startswith(root_path + os.sep):
            raise HomeAssistantError(f"Not a local media item: {media_id}")
        return Path(path)

    # Files and state

    def _read_current(self) -> tuple[bytes | None, bytes | None]:
        def read(name: str) -> bytes | None:
            try:
                return (self.dir / name).read_bytes()
            except OSError:
                return None

        return read("strip.png"), read("preview.gif")

    def _write(self, key: str, result: convert.Converted) -> None:
        (self.dir / "history").mkdir(parents=True, exist_ok=True)
        _write_atomic(self.dir / "strip.png", result.strip)
        _write_atomic(self.dir / "preview.gif", result.preview)
        _write_atomic(self.thumb_path(key), result.thumb)

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(
            lambda: {"history": self.history, "current": self.current, "showing": self.showing}, 1
        )

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(entry_id=self.entry.entry_id))


def _read_limited(path: Path) -> bytes:
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HomeAssistantError("The file is larger than 20 MB")
    return data


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _remove(path: Path) -> None:
    path.unlink(missing_ok=True)
