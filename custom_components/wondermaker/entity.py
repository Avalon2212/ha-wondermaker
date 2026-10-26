"""Basis-Entität."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import WondermakerCoordinator


class WondermakerEntity(CoordinatorEntity[WondermakerCoordinator]):
    """Gemeinsame Basis aller Entitäten."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WondermakerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info
