"""Constants for ESPHome Pixoo Gallery."""

from __future__ import annotations

DOMAIN = "esphome_pixoo_gallery"

CONF_DEVICE_ID = "device_id"
CONF_ACTION_PREFIX = "action_prefix"
CONF_BASE_URL = "base_url"
CONF_TOKEN = "token"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_URL = "url"
ATTR_MEDIA = "media"
ATTR_TEXT = "text"
ATTR_COLOR = "color"
ATTR_KEY = "key"

DEFAULT_COLOR = (255, 170, 0)
HISTORY_MAX = 40
MAX_BYTES = 20 * 1024 * 1024
UPLOAD_DIR = DOMAIN
UPLOAD_TYPES = {"image/gif": "gif", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

CARD_URL = f"/{DOMAIN}/esphome-pixoo-gallery-card.js"
STRIP_URL = f"/api/{DOMAIN}/strip/{{token}}"
THUMB_URL = f"/api/{DOMAIN}/{{entry_id}}/history/{{key}}"
UPLOAD_URL = f"/api/{DOMAIN}/upload"

SIGNAL_UPDATED = f"{DOMAIN}_updated_{{entry_id}}"
