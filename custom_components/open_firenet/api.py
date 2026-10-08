"""HTTP client for the Open Firenet bridge.

Extracts all HTTP concerns out of the coordinator and reuses a single,
persistent aiohttp session (opened lazily, closed on unload) instead of
creating a new session on every poll.

The persistent-session / client-extraction design is adapted from the
refactor proposed by @sguernion in PR #3, ported onto the v2 unified
`/api/state` API.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_CONTROLS, API_SCHEDULE, API_STATE


class BridgeRefusedName(Exception):
    """403: the bridge does not answer under the name it was called by (bridge firmware 4.0 and later).

    It only answers at its IP address, at a ".local" name, or under a name its owner added on its page.
    """

    def __init__(self, host: str, ip: str) -> None:
        super().__init__(f"the bridge refuses the name {host}")
        self.host = host
        self.ip = ip


class StoveNotReady(Exception):
    """503: the stove is not linked, or has not sent its settings yet. Nothing was sent to the stove."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("the stove is not ready")
        self.retry_after = retry_after


async def _raise_for_refusal(resp: aiohttp.ClientResponse) -> None:
    """Turn the bridge's two explicit refusals into their own errors; any other error status as usual."""
    if resp.status == 403:
        try:
            body = await resp.json(content_type=None)
        except (ValueError, aiohttp.ClientError):
            body = None
        if isinstance(body, dict) and body.get("refused") == "host":
            raise BridgeRefusedName(str(body.get("host", "")), str(body.get("ip", "")))
    if resp.status == 503:
        try:
            body = await resp.json(content_type=None)
        except (ValueError, aiohttp.ClientError):
            body = None
        if isinstance(body, dict) and body.get("error") == "stove_not_ready":
            try:
                retry_after = float(resp.headers.get("Retry-After", "5"))
            except ValueError:
                retry_after = 5.0
            raise StoveNotReady(retry_after)
    resp.raise_for_status()


# A command refused because the stove is not ready is sent again once, after the delay the bridge gives.
_MAX_RETRY_DELAY = 10.0


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
            await _raise_for_refusal(resp)
            return await resp.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> None:
        for attempt in (1, 2):
            try:
                async with self._get_session().post(
                    f"{self._base}{path}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    await _raise_for_refusal(resp)
                return
            except StoveNotReady as err:
                if attempt == 2:
                    raise
                await asyncio.sleep(min(max(err.retry_after, 0.0), _MAX_RETRY_DELAY))

    async def set_controls(self, payload: dict[str, Any]) -> None:
        """POST a partial controls update as JSON to /api/controls."""
        await self._post(API_CONTROLS, payload)

    async def fetch_schedule(self) -> dict[str, Any]:
        """GET the weekly schedule payload from /api/schedule."""
        async with self._get_session().get(f"{self._base}{API_SCHEDULE}") as resp:
            await _raise_for_refusal(resp)
            return await resp.json()

    async def set_schedule(self, payload: dict[str, Any]) -> None:
        """POST a schedule update as JSON to /api/schedule."""
        await self._post(API_SCHEDULE, payload)
