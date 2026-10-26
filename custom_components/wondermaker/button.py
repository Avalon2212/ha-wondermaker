"""Buttons des WonderMaker."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MoonrakerClient, MoonrakerError
from .coordinator import WondermakerCoordinator
from .entity import WondermakerEntity


@dataclass(frozen=True, kw_only=True)
class WMButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[MoonrakerClient], Awaitable[None]]


BUTTONS: tuple[WMButtonDescription, ...] = (
    WMButtonDescription(key="pause", translation_key="pause", press_fn=lambda c: c.pause()),
    WMButtonDescription(key="resume", translation_key="resume", press_fn=lambda c: c.resume()),
    WMButtonDescription(key="cancel", translation_key="cancel", press_fn=lambda c: c.cancel()),
    WMButtonDescription(
        key="home", translation_key="home", press_fn=lambda c: c.gcode("G28", timeout=180)
    ),
    WMButtonDescription(
        key="emergency_stop",
        translation_key="emergency_stop",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.emergency_stop(),
    ),
    WMButtonDescription(
        key="firmware_restart",
        translation_key="firmware_restart",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.firmware_restart(),
    ),
    WMButtonDescription(
        key="klipper_restart",
        translation_key="klipper_restart",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.klipper_restart(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WondermakerCoordinator = entry.runtime_data
    async_add_entities(WondermakerButton(coordinator, d) for d in BUTTONS)
    async_add_entities([WondermakerTestNotificationButton(coordinator)])


class WondermakerButton(WondermakerEntity, ButtonEntity):
    entity_description: WMButtonDescription

    def __init__(self, coordinator: WondermakerCoordinator, description: WMButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator.client)
        except MoonrakerError as err:
            raise HomeAssistantError(f"{self.entity_description.key}: {err}") from err
        await self.coordinator.async_request_refresh()


class WondermakerTestNotificationButton(WondermakerEntity, ButtonEntity):
    """Sendet eine Test-Benachrichtigung mit aktuellem Kamerabild."""

    _attr_translation_key = "test_notification"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: WondermakerCoordinator) -> None:
        super().__init__(coordinator, "test_notification")

    async def async_press(self) -> None:
        await self.coordinator.events.async_send_test()
