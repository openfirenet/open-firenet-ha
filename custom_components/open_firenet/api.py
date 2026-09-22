"""HTTP client for the Open-Firenet bridge.

Extracts all HTTP concerns out of the coordinator and reuses a single,
persistent aiohttp session (opened lazily, closed on unload) instead of
creating a new session on every poll.

The persistent-session / client-extraction design is adapted from the
refactor proposed by @sguernion in PR #3, ported onto the v2 unified
`/api/state` API.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import API_CONTROLS, API_SCHEDULE, API_STATE


class OpenFirenetClient:
    """Thin async client around the bridge's REST API (single session)."""

    def __init__(self, host: str) -> None:
        self._base = f"http://{host}"
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def async_validate(self) -> bool:
        """Return True if the host answers a valid v2 state payload."""
        data = await self.fetch_state()
        return isinstance(data, dict) and "device" in data

    async def fetch_state(self) -> dict[str, Any]:
        """GET the unified /api/state payload (device / stove / sensors / controls)."""
        async with self._get_session().get(f"{self._base}{API_STATE}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def set_controls(self, payload: dict[str, Any]) -> None:
        """POST a partial controls update as JSON to /api/controls."""
        async with self._get_session().post(
            f"{self._base}{API_CONTROLS}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()

    async def fetch_schedule(self) -> dict[str, Any]:
        """GET the weekly schedule payload from /api/schedule."""
        async with self._get_session().get(f"{self._base}{API_SCHEDULE}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def set_schedule(self, payload: dict[str, Any]) -> None:
        """POST a schedule update as JSON to /api/schedule."""
        async with self._get_session().post(
            f"{self._base}{API_SCHEDULE}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
