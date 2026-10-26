"""Vorschaubild (Thumbnail) des aktuellen Druckauftrags."""

from __future__ import annotations

import logging
import posixpath

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import MoonrakerError
from .coordinator import WondermakerCoordinator, get_status

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            WondermakerCoverImage(hass, entry.runtime_data),
            WondermakerEventPhoto(hass, entry.runtime_data, "print"),
            WondermakerEventPhoto(hass, entry.runtime_data, "error"),
        ]
    )


class WondermakerCoverImage(CoordinatorEntity[WondermakerCoordinator], ImageEntity):
    """Zeigt das im G-Code eingebettete Vorschaubild des aktuellen Drucks."""

    _attr_has_entity_name = True
    _attr_translation_key = "cover_image"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, coordinator: WondermakerCoordinator) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_cover_image"
        self._attr_device_info = coordinator.device_info
        self._filename: str | None = None
        self._cached: bytes | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        filename = get_status(self.coordinator.data, "print_stats", "filename") or None
        if filename != self._filename:
            self._filename = filename
            self._cached = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        if self._cached is not None:
            return self._cached
        filename = self._filename or (
            get_status(self.coordinator.data, "print_stats", "filename") or None
        )
        if not filename:
            return None
        client = self.coordinator.client
        try:
            meta = await client.file_metadata(filename)
            thumbs = meta.get("thumbnails") or []
            if not thumbs:
                return None
            best = max(thumbs, key=lambda t: t.get("width", 0) * t.get("height", 0))
            path = posixpath.join(posixpath.dirname(filename), best["relative_path"])
            self._cached = await client.get_gcode_file(path)
        except (MoonrakerError, KeyError) as err:
            _LOGGER.debug("Thumbnail nicht ladbar: %s", err)
            return None
        return self._cached


class WondermakerEventPhoto(CoordinatorEntity[WondermakerCoordinator], ImageEntity):
    """Kamerabild vom letzten Druckende bzw. vom letzten Fehler."""

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator: WondermakerCoordinator, kind: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._kind = kind
        self._attr_translation_key = f"{kind}_photo"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{kind}_photo"
        self._attr_device_info = coordinator.device_info
        self._seen = None

    def _stamp(self):
        entry = self.coordinator.events.photos.get(self._kind)
        return entry[1] if entry else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.hass.async_add_executor_job(
            self.coordinator.events.load_saved_photo, self._kind
        )
        self._seen = self._stamp()
        self._attr_image_last_updated = self._seen
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        stamp = self._stamp()
        if stamp != self._seen:
            self._seen = stamp
            self._attr_image_last_updated = stamp
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        entry = self.coordinator.events.photos.get(self._kind)
        return entry[0] if entry else None
