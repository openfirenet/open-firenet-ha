from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BridgeRefusedName, OpenFirenetClient, StoveNotReady
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


# Command keys whose /api/state name is not a plain snake_case of the command key.
_STATE_KEY_ALIASES = {
    "setBackTemp": "setback_temperature",
    "frostProtectionTemp": "frost_protection_temperature",
    "roomTempOffset": "room_temperature_offset",
    "bakeTarget": "bake_target_temperature",
}


def _to_snake(key: str) -> str:
    return _STATE_KEY_ALIASES.get(key) or _CAMEL_BOUNDARY.sub("_", key).lower()


class OpenFirenetCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, host: str, scan_interval: int) -> None:
        self.host = host
        self._client = OpenFirenetClient(host)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict:
        try:
            async with asyncio.timeout(10):
                return await self._client.fetch_state()
        except BridgeRefusedName as err:
            raise UpdateFailed(
                f"The bridge does not answer under the name {err.host or self.host}. Open its page by its IP address"
                f"{' (http://' + err.ip + ')' if err.ip else ''} and add this name in the Bridge tab, section Access,"
                " or set up this integration again with the IP address."
            ) from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout connecting to {self.host}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with {self.host}: {err}") from err

    async def async_set_controls(self, **kwargs) -> None:
        # A command that the bridge refuses or that cannot reach it is shown as a message, not as a raw HTTP error.
        try:
            await self._client.set_controls(kwargs)
        except StoveNotReady as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="stove_not_ready") from err
        except BridgeRefusedName as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="name_refused",
                translation_placeholders={"host": err.host or self.host, "ip": err.ip or "?"},
            ) from err
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"host": self.host, "error": str(err) or type(err).__name__},
            ) from err
        # /api/state exposes controls in snake_case while commands are sent in camelCase,
        # and entities read the snake_case key first: write both so the optimistic value
        # is actually visible, then re-read the device (its model is updated on POST).
        if self.data and "controls" in self.data:
            current_controls = self.data["controls"].copy()
            for key, value in kwargs.items():
                current_controls[key] = value
                current_controls[_to_snake(key)] = value
            self.async_set_updated_data({**self.data, "controls": current_controls})
        await self.async_refresh()
