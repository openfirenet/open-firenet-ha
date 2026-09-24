"""Test fixtures: a fake Open-Firenet bridge that behaves like the ESP firmware.

The real bridge exposes controls in snake_case on GET /api/state, accepts camelCase
commands on POST /api/controls and updates its own model immediately on POST.
"""

from __future__ import annotations

import copy

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.open_firenet.const import DOMAIN

INITIAL_STATE = {
    "device": {"name": "Open-Firenet", "version": "2.1.0", "connected": True},
    "stove": {
        "state": "off",
        "state_code": 0,
        "state_label": "Off",
        "sub_state": 0,
        "is_burning": False,
        "has_error": False,
        "error_code": 0,
        "error_sub": 0,
        "model": 0,
        "model_name": "DOMO",
        "mainboard_version": "1.00",
        "firmware_build": "1",
    },
    "sensors": {
        "room_temperature": 20.0,
        "combustion_temperature": 20.0,
        "board_temperature": 20.0,
        "pellets_total_kg": 0,
        "pellet_hours": 0,
        "service_countdown_kg": 0,
        "fan_speed_rpm": 0,
        "auger_speed_rpm": 0,
    },
    "controls": {
        "on": False,
        "mode": "manual",
        "mode_code": 0,
        "target_temperature": 21.0,
        "power_percent": 70,
        "heating_times_active": False,
        "setback_temperature": 16.0,
        "convection_fan1_active": True,
        "convection_fan1_level": 2,
        "convection_fan1_area": 0,
        "convection_fan2_active": True,
        "convection_fan2_level": 3,
        "convection_fan2_area": 0,
        "frost_protection_active": False,
        "frost_protection_temperature": 5.0,
        "bake_target_temperature": 180,
        "room_temperature_offset": 0.0,
    },
    "controls_pos": [],
    "sensors_pos": [],
}

# camelCase command key -> snake_case key of /api/state "controls"
COMMAND_TO_STATE_KEY = {
    "on": "on",
    "power_percent": "power_percent",
    "convectionFan1Active": "convection_fan1_active",
    "convectionFan1Level": "convection_fan1_level",
    "convectionFan2Active": "convection_fan2_active",
    "convectionFan2Level": "convection_fan2_level",
    "heatingTimesActive": "heating_times_active",
    "frostProtectionActive": "frost_protection_active",
    "convectionFan1Area": "convection_fan1_area",
    "convectionFan2Area": "convection_fan2_area",
    "setback_temperature": "setback_temperature",
    "frostProtectionTemp": "frost_protection_temperature",
    "room_temperature_offset": "room_temperature_offset",
    "bakeTarget": "bake_target_temperature",
}


class FakeBridge:
    def __init__(self) -> None:
        self.state = copy.deepcopy(INITIAL_STATE)
        self.posts: list[dict] = []
        self.gets = 0
        self.fail_posts = False
        self.max_fan_level = 5  # firmware-side clamp, lets tests prove the device wins

    async def _get_state(self, request: web.Request) -> web.Response:
        self.gets += 1
        return web.json_response(self.state)

    async def _post_controls(self, request: web.Request) -> web.Response:
        if self.fail_posts:
            return web.Response(status=500)
        payload = await request.json()
        self.posts.append(payload)
        for key, value in payload.items():
            state_key = COMMAND_TO_STATE_KEY.get(key)
            if state_key is None:
                continue
            if state_key.endswith("_level"):
                value = min(int(value), self.max_fan_level)
            self.state["controls"][state_key] = value
        return web.json_response({"ok": True})

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/api/state", self._get_state)
        app.router.add_post("/api/controls", self._post_controls)
        return app


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def bridge(socket_enabled):
    fake = FakeBridge()
    server = TestServer(fake.app())
    await server.start_server()
    fake.host = f"{server.host}:{server.port}"
    yield fake
    await server.close()


@pytest.fixture
async def setup_integration(hass, bridge, request):
    if getattr(request, "param", None) == "domo_back":
        bridge.state["stove"]["model_name"] = "DOMO BACK"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: bridge.host, CONF_SCAN_INTERVAL: 300},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
