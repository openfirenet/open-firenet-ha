from __future__ import annotations

import asyncio
import logging

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import BridgeRefusedName, OpenFirenetClient
from .const import CONF_EXTERNAL_TEMP_SENSOR, CONF_SCHEDULE_ENTITY, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=300)
        ),
    }
)


class OpenFirenetConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OpenFirenetOptionsFlow()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip().rstrip("/")
            client = OpenFirenetClient(host)
            try:
                async with asyncio.timeout(8):
                    if not await client.async_validate():
                        errors["base"] = "invalid_response"
            except BridgeRefusedName:
                errors["base"] = "name_refused"
            except asyncio.TimeoutError:
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Open Firenet ({host})",
                    data={CONF_HOST: host, CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SCHEMA,
            errors=errors,
        )


class OpenFirenetOptionsFlow(OptionsFlow):
    """Options: an optional Home Assistant temperature sensor for the climate entity's current temperature, and
    an optional Home Assistant schedule that the "copy" button sends to the stove."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_EXTERNAL_TEMP_SENSOR)
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_EXTERNAL_TEMP_SENSOR,
                    description={"suggested_value": current},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Optional(
                    CONF_SCHEDULE_ENTITY,
                    description={"suggested_value": self.config_entry.options.get(CONF_SCHEDULE_ENTITY)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="schedule")),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
