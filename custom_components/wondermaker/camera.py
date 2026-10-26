"""Webcam des WonderMaker (aus der Moonraker-Webcam-Konfiguration)."""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_aiohttp_proxy_web,
    async_get_clientsession,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MoonrakerError
from .coordinator import WondermakerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WondermakerCoordinator = entry.runtime_data
    try:
        webcams = await coordinator.client.webcams()
    except MoonrakerError as err:
        _LOGGER.debug("Keine Webcams abrufbar: %s", err)
        return
    async_add_entities(
        WondermakerCamera(coordinator, cam)
        for cam in webcams
        if cam.get("enabled", True) and (cam.get("stream_url") or cam.get("snapshot_url"))
    )


class WondermakerCamera(Camera):
    """MJPEG-Webcam: Snapshot und Live-Stream werden durch HA geleitet."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WondermakerCoordinator, cam: dict) -> None:
        super().__init__()
        self._coordinator = coordinator
        client = coordinator.client
        self._stream_urls = self._candidates(client, cam.get("stream_url"))
        self._snapshot_urls = self._candidates(client, cam.get("snapshot_url"))
        self._working: int | None = None
        name = cam.get("name") or "webcam"
        self._attr_name = "Kamera" if name.lower() in ("camera", "webcam") else f"Kamera {name}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_cam_{name}"
        self._attr_device_info = coordinator.device_info

    @staticmethod
    def _candidates(client, url: str | None) -> list[str]:
        return client.candidate_urls(url)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        order = list(range(len(self._snapshot_urls)))
        if self._working in order:
            order.remove(self._working)
            order.insert(0, self._working)
        for i in order:
            try:
                image = await self._coordinator.client.get_url_bytes(self._snapshot_urls[i])
            except MoonrakerError as err:
                _LOGGER.debug("Snapshot %s fehlgeschlagen: %s", self._snapshot_urls[i], err)
                continue
            self._working = i
            return image
        return None

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        if not self._stream_urls:
            return await super().handle_async_mjpeg_stream(request)
        if self._working is None:
            await self.async_camera_image()  # findet die erreichbare Adresse
        index = self._working or 0
        index = min(index, len(self._stream_urls) - 1)
        session = async_get_clientsession(self.hass)
        coro = session.get(self._stream_urls[index], timeout=None)
        return await async_aiohttp_proxy_web(self.hass, request, coro)
