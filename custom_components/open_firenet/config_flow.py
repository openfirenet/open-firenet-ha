from __future__ import annotations

import asyncio
import logging

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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

    async def _check_host(self, host: str) -> str | None:
        """Ask the bridge at this address whether it answers: None when it does, else the key of the error."""
        client = OpenFirenetClient(host, async_get_clientsession(self.hass))
        try:
            async with asyncio.timeout(8):
                if not await client.async_validate():
                    return "invalid_response"
        except BridgeRefusedName:
            return "name_refused"
        except asyncio.TimeoutError:
            return "cannot_connect"
        except aiohttp.ClientError:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error during config flow")
            return "unknown"
        finally:
            await client.close()
        return None

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip().rstrip("/")
            error = await self._check_host(host)
            if error:
                errors["base"] = error
            else:
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

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        """Change the address of a bridge already added (menu "Reconfigure"), for instance after the router gave
        it another IP address. The entry and its entities are kept: only the address and the title change."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip().rstrip("/")
            others = [e for e in self.hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]
            if any(e.unique_id == host or e.data.get(CONF_HOST) == host for e in others):
                return self.async_abort(reason="already_configured")
            error = await self._check_host(host)
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_HOST: host},
                    title=f"Open Firenet ({host})",
                    unique_id=host,
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=(user_input or entry.data)[CONF_HOST]): str}
            ),
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
