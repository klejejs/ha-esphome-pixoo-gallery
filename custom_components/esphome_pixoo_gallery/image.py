"""An image entity with what the display shows now."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GalleryConfigEntry
from .const import SIGNAL_UPDATED
from .gallery import Gallery


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GalleryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([GalleryImage(hass, entry.runtime_data)])


class GalleryImage(ImageEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "current"
    _attr_content_type = "image/gif"

    def __init__(self, hass: HomeAssistant, gallery: Gallery) -> None:
        super().__init__(hass)
        self._gallery = gallery
        self._attr_unique_id = gallery.entry.entry_id
        self._attr_image_last_updated = gallery.updated
        # Join the ESPHome device instead of making a device of its own.
        device = dr.async_get(hass).async_get(gallery.device_id)
        if device is not None:
            self._attr_device_info = DeviceInfo(connections=device.connections, identifiers=device.identifiers)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATED.format(entry_id=self._gallery.entry.entry_id),
                self._updated,
            )
        )

    @callback
    def _updated(self) -> None:
        if self._attr_image_last_updated != self._gallery.updated:
            self._attr_image_last_updated = self._gallery.updated
            self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._gallery.preview
