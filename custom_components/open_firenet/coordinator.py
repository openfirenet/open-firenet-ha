from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from datetime import time

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BridgeRefusedName, OpenFirenetClient, StoveNotReady
from .const import DOMAIN
from .schedule import (
    SLOT_COUNT,
    TooManySlots,
    command_key,
    decode_slot,
    encode_slot,
    slots_from_ha_schedule,
    slots_from_state,
)

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
        self._client = OpenFirenetClient(host, async_get_clientsession(hass))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        # Schedule times changed in Home Assistant and not sent to the stove yet: (slot index, "start" | "end") -> time.
        self._schedule_pending: dict[tuple[int, str], time] = {}

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

    # --- heating schedule (see schedule.py) ---------------------------------------------------------------------

    @property
    def schedule_has_pending(self) -> bool:
        return bool(self._schedule_pending)

    def schedule_time(self, index: int, edge: str) -> time | None:
        """Start or end of a slot: the pending change if there is one, else the stove's value."""
        pending = self._schedule_pending.get((index, edge))
        if pending is not None:
            return pending
        slots = slots_from_state(self.data)
        decoded = decode_slot(slots[index]) if slots else None
        if decoded is None:
            return None
        return decoded[0] if edge == "start" else decoded[1]

    def schedule_set_pending(self, index: int, edge: str, value: time) -> None:
        """Keep a changed time; nothing is sent to the stove before schedule_send()."""
        self._schedule_pending[(index, edge)] = value.replace(second=0, microsecond=0)
        self.async_update_listeners()

    def schedule_discard(self) -> None:
        self._schedule_pending.clear()
        self.async_update_listeners()

    async def schedule_send(self) -> None:
        """Send every slot that has a pending change, in one command."""
        slots = slots_from_state(self.data)
        if slots is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="stove_not_ready")
        command: dict[str, int] = {}
        for index in sorted({i for i, _ in self._schedule_pending}):
            start, end = self.schedule_time(index, "start"), self.schedule_time(index, "end")
            if start is None or end is None:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="stove_not_ready")
            try:
                command[command_key(index)] = encode_slot(start, end)
            except ValueError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="schedule_end_before_start",
                    translation_placeholders={
                        "start": start.strftime("%H:%M"),
                        "end": end.strftime("%H:%M"),
                        "slot": command_key(index).removeprefix("heatTime"),
                    },
                ) from err
        if not command:
            return
        await self.async_set_controls(**command)
        self._schedule_pending.clear()
        self.async_update_listeners()

    async def schedule_copy_from(self, schedule_entity: str | None) -> None:
        """Send the weekly plan of a Home Assistant schedule to the stove: all 14 slots, in one command."""
        if not schedule_entity:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="schedule_not_chosen")
        if self.hass.states.get(schedule_entity) is None or not self.hass.services.has_service("schedule", "get_schedule"):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="schedule_not_found",
                translation_placeholders={"entity": schedule_entity},
            )
        response = await self.hass.services.async_call(
            "schedule", "get_schedule", {"entity_id": schedule_entity}, blocking=True, return_response=True
        )
        plan = (response or {}).get(schedule_entity)
        if not isinstance(plan, dict):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="schedule_not_found",
                translation_placeholders={"entity": schedule_entity},
            )
        try:
            slots = slots_from_ha_schedule(plan)
        except TooManySlots as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="schedule_too_many_slots",
                translation_placeholders={"weekday": err.weekday, "count": str(err.count)},
            ) from err
        await self.async_set_controls(**{command_key(i): slots[i] for i in range(SLOT_COUNT)})
        self._schedule_pending.clear()
        self.async_update_listeners()
