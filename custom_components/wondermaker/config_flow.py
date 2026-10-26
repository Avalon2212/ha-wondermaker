"""Config Flow für den WonderMaker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import MoonrakerAuthError, MoonrakerClient, MoonrakerError
from .const import (
    CONF_API_KEY,
    CONF_FINISH_TIME_ENABLED,
    CONF_FINISH_TIME_INTERVAL,
    CONF_LAYER_ENABLED,
    CONF_LAYER_INTERVAL,
    CONF_NOTIFY_DELAY,
    CONF_NOTIFY_DOOR,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_ERROR,
    CONF_NOTIFY_ERROR_IMAGE,
    CONF_NOTIFY_FILAMENT,
    CONF_NOTIFY_IMAGE,
    CONF_NOTIFY_TARGETS,
    CONF_SCAN_INTERVAL,
    DEFAULT_FINISH_TIME_INTERVAL,
    DEFAULT_LAYER_INTERVAL,
    DEFAULT_NOTIFY_DELAY,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class WondermakerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung über die Oberfläche."""

    VERSION = 1

    async def _validate(
        self, host: str, port: int, api_key: str | None
    ) -> str | None:
        client = MoonrakerClient(async_get_clientsession(self.hass), host, port, api_key)
        try:
            await client.server_info()
        except MoonrakerAuthError:
            return "invalid_auth"
        except MoonrakerError:
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            api_key = user_input.get(CONF_API_KEY) or None

            await self.async_set_unique_id(f"{host}:{port}".lower())
            self._abort_if_unique_id_configured()

            error = await self._validate(host, port, api_key)
            if error is None:
                data = {CONF_HOST: host, CONF_PORT: port}
                if api_key:
                    data[CONF_API_KEY] = api_key
                return self.async_create_entry(
                    title=f"WonderMaker ZR Ultra S ({host})", data=data
                )
            errors["base"] = error

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_API_KEY): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            error = await self._validate(
                entry.data[CONF_HOST], entry.data[CONF_PORT], api_key
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return WondermakerOptionsFlow()


def _number(minimum: int, maximum: int) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        )
    )


class WondermakerOptionsFlow(OptionsFlow):
    """Einstellungen: Allgemein und Benachrichtigung nach Druckende."""

    def _save(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        cleaned = {
            k: (int(v) if isinstance(v, float) else v) for k, v in user_input.items()
        }
        return self.async_create_entry(data={**self.config_entry.options, **cleaned})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["general", "notifications"]
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): _number(2, 120),
                    vol.Required(
                        CONF_FINISH_TIME_ENABLED,
                        default=opts.get(
                            CONF_FINISH_TIME_ENABLED,
                            opts.get(CONF_FINISH_TIME_INTERVAL, DEFAULT_FINISH_TIME_INTERVAL) != 0,
                        ),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_FINISH_TIME_INTERVAL,
                        default=opts.get(CONF_FINISH_TIME_INTERVAL) or DEFAULT_FINISH_TIME_INTERVAL,
                    ): _number(1, 3600),
                    vol.Required(
                        CONF_LAYER_ENABLED,
                        default=opts.get(
                            CONF_LAYER_ENABLED,
                            opts.get(CONF_LAYER_INTERVAL, DEFAULT_LAYER_INTERVAL) != 0,
                        ),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_LAYER_INTERVAL,
                        default=opts.get(CONF_LAYER_INTERVAL) or DEFAULT_LAYER_INTERVAL,
                    ): _number(1, 3600),
                }
            ),
        )

    def _notify_services(self) -> list[SelectOptionDict]:
        """Alle verfügbaren notify-Dienste (Handy-Apps, Telegram, ...)."""
        services = self.hass.services.async_services().get("notify", {})
        names = {n for n in services if n not in ("send_message", "notify")}
        names |= set(self.config_entry.options.get(CONF_NOTIFY_TARGETS) or [])
        return [
            SelectOptionDict(value=n, label=n.replace("_", " ").title())
            for n in sorted(names)
        ]

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input.setdefault(CONF_NOTIFY_TARGETS, [])
            return self._save(user_input)
        opts = self.config_entry.options

        def flag(key: str, default: bool):
            return vol.Required(key, default=opts.get(key, default))

        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NOTIFY_TARGETS,
                        default=opts.get(CONF_NOTIFY_TARGETS, []),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=self._notify_services(),
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    flag(CONF_NOTIFY_ENABLED, False): BooleanSelector(),
                    flag(CONF_NOTIFY_IMAGE, True): BooleanSelector(),
                    vol.Required(
                        CONF_NOTIFY_DELAY,
                        default=opts.get(CONF_NOTIFY_DELAY, DEFAULT_NOTIFY_DELAY),
                    ): _number(0, 120),
                    flag(CONF_NOTIFY_ERROR, False): BooleanSelector(),
                    flag(CONF_NOTIFY_ERROR_IMAGE, False): BooleanSelector(),
                    flag(CONF_NOTIFY_FILAMENT, False): BooleanSelector(),
                    flag(CONF_NOTIFY_DOOR, False): BooleanSelector(),
                }
            ),
        )
