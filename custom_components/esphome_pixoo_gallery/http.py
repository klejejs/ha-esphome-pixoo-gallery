"""HTTP endpoints: the strip for the display, history thumbnails and uploads."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, MAX_BYTES, UPLOAD_DIR, UPLOAD_TYPES, UPLOAD_URL
from .gallery import Gallery

NO_STORE = {"Cache-Control": "no-store"}


@callback
def async_register(hass: HomeAssistant) -> None:
    hass.http.register_view(StripView())
    hass.http.register_view(ThumbView())
    hass.http.register_view(UploadView())


def galleries(hass: HomeAssistant) -> list[Gallery]:
    return [entry.runtime_data for entry in hass.config_entries.async_loaded_entries(DOMAIN)]


class StripView(HomeAssistantView):
    """The display downloads its picture here without a login, so the URL carries a secret token."""

    url = f"/api/{DOMAIN}/strip/{{token}}"
    name = f"api:{DOMAIN}:strip"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        for gallery in galleries(request.app["hass"]):
            if secrets.compare_digest(gallery.token, token) and gallery.strip is not None:
                return web.Response(body=gallery.strip, content_type="image/png", headers=NO_STORE)
        return web.Response(status=404)


class ThumbView(HomeAssistantView):
    url = f"/api/{DOMAIN}/{{entry_id}}/history/{{key}}"
    name = f"api:{DOMAIN}:history"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, key: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if len(key) != 12 or not all(c in "0123456789abcdef" for c in key):
            return web.Response(status=404)
        for gallery in galleries(hass):
            if gallery.entry.entry_id == entry_id:
                path = gallery.thumb_path(key)
                data = await hass.async_add_executor_job(_read, path)
                if data is None:
                    break
                return web.Response(
                    body=data, content_type="image/gif", headers={"Cache-Control": "private, max-age=86400"}
                )
        return web.Response(status=404)


class UploadView(HomeAssistantView):
    """Upload for any logged-in user; Home Assistant's own media upload is admin-only."""

    url = UPLOAD_URL
    name = f"api:{DOMAIN}:upload"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        media_dir = hass.config.media_dirs.get("local")
        if media_dir is None:
            return self.json_message("Home Assistant has no local media folder", 500)

        reader = await request.multipart()
        field = await reader.next()
        while field is not None and field.name != "file":
            field = await reader.next()
        if field is None:
            return self.json_message("No file", 400)
        ext = UPLOAD_TYPES.get((field.headers.get("Content-Type") or "").split(";")[0].strip())
        if ext is None:
            return self.json_message("Only GIF, PNG, JPEG or WebP images", 415)

        data = bytearray()
        while chunk := await field.read_chunk():
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                return self.json_message("The file is larger than 20 MB", 413)

        name = f"pixoo-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.{ext}"
        folder = Path(media_dir) / UPLOAD_DIR

        def write() -> None:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(data)

        await hass.async_add_executor_job(write)
        return self.json({"media_content_id": f"media-source://media_source/local/{UPLOAD_DIR}/{name}"})


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None
