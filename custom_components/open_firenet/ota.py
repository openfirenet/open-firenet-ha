"""Wireless update of the bridge: download and check a firmware, then send it with the ArduinoOTA protocol.

Same steps and same checks as the installer (open-firenet-installer, flasher_ota.rs and github.rs):
the firmware is only sent when its SHA-256 is in a SHA256SUMS list signed with the official minisign key."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass

import aiohttp
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_LOGGER = logging.getLogger(__name__)

# Public key the releases are signed with (same as the installer's minisign.pub).
OFFICIAL_PUBLIC_KEY = "RWQhzS5dR0kodMCMiFMESBDRDhxMyRaA4yNbIcAMD2B9kQS21I+FABT4"

OTA_PORT = 3232  # UDP port of the update service of the bridge
CHUNK_SIZE = 1024
INVITATION_TRIES = 8
INVITATION_TIMEOUT = 1.5  # seconds per try
AUTH_TIMEOUT = 12  # the bridge needs a few seconds to check a password
CONNECT_BACK_TIMEOUT = 15  # time the bridge has to open its connection back to Home Assistant
CHUNK_TIMEOUT = 15
FINAL_TIMEOUT = 8
MAX_FIRMWARE_BYTES = 4 * 1024 * 1024  # the flash of the bridge is 4 MB
ESP_IMAGE_MAGIC = 0xE9


class OtaError(Exception):
    """A failed update. `key` names the translated message, `placeholders` its values."""

    def __init__(self, key: str, **placeholders: str) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders


# --- download and checks ----------------------------------------------------------------------------------------


def _decode_minisign_key(public_key: str) -> tuple[bytes, bytes]:
    raw = base64.b64decode(public_key)
    if len(raw) != 42 or raw[:2] != b"Ed":
        raise OtaError("update_signature_invalid")
    return raw[2:10], raw[10:42]


def verify_minisign(message: bytes, signature_text: str, public_key: str = OFFICIAL_PUBLIC_KEY) -> None:
    """Check a minisign signature file over `message`; raises OtaError when it is not valid for this key.

    Both the signature of the message and the one of the "trusted comment" are checked."""
    try:
        key_id, key = _decode_minisign_key(public_key)
        lines = [line.strip() for line in signature_text.strip().splitlines()]
        if len(lines) < 4 or not lines[2].startswith("trusted comment:"):
            raise OtaError("update_signature_invalid")
        raw = base64.b64decode(lines[1])
        algorithm, signature_key_id, signature = raw[:2], raw[2:10], raw[10:74]
        if len(raw) != 74 or algorithm not in (b"Ed", b"ED") or signature_key_id != key_id:
            raise OtaError("update_signature_invalid")
        trusted_comment = lines[2][len("trusted comment:"):].lstrip(" ").encode()
        global_signature = base64.b64decode(lines[3])
        signed = hashlib.blake2b(message).digest() if algorithm == b"ED" else message
        verifier = Ed25519PublicKey.from_public_bytes(key)
        verifier.verify(signature, signed)
        verifier.verify(global_signature, signature + trusted_comment)
    except OtaError:
        raise
    except (InvalidSignature, ValueError):
        raise OtaError("update_signature_invalid") from None


def checksum_of(sums: str, name: str) -> str | None:
    """The SHA-256 listed for a file in a SHA256SUMS text."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def find_assets(assets: dict[str, str], variant: str = "standard") -> tuple[str, str, str, str]:
    """(firmware name, firmware url, sums url, signature url) of a release, or OtaError."""
    if variant == "psram":
        firmware = next((n for n in assets if "ota-psram" in n and n.endswith(".bin")), None)
        if firmware is None:
            firmware = next(
                (n for n in assets if "psram" in n and n.endswith(".bin") and "factory" not in n and "bootloader" not in n),
                None,
            )
        # Fallback to standard if no PSRAM binary exists in this release (e.g. older release)
        if firmware is None:
            _LOGGER.warning("No PSRAM firmware asset in release, falling back to standard binary")
            firmware = next((n for n in assets if "ota" in n and "psram" not in n and n.endswith(".bin")), None)
            if firmware is None:
                firmware = next(
                    (n for n in assets if n.endswith(".bin") and "psram" not in n and "factory" not in n and "bootloader" not in n),
                    None,
                )
    else:
        firmware = next((n for n in assets if "ota" in n and "psram" not in n and n.endswith(".bin")), None)
        if firmware is None:
            firmware = next(
                (n for n in assets if n.endswith(".bin") and "psram" not in n and "factory" not in n and "bootloader" not in n),
                None,
            )
    sums = next((n for n in assets if n == "SHA256SUMS"), None)
    signature = next((n for n in assets if n.endswith(".minisig")), None)
    if not (firmware and sums and signature):
        raise OtaError("update_assets_missing")
    return firmware, assets[firmware], assets[sums], assets[signature]


async def _download(session: aiohttp.ClientSession, url: str, limit: int) -> bytes:
    try:
        async with asyncio.timeout(120):
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise OtaError("update_download_failed", error=f"HTTP {resp.status}")
                data = bytearray()
                async for part in resp.content.iter_chunked(64 * 1024):
                    data += part
                    if len(data) > limit:
                        break
    except (asyncio.TimeoutError, aiohttp.ClientError) as err:
        raise OtaError("update_download_failed", error=str(err) or type(err).__name__) from err
    if len(data) > limit:
        raise OtaError("update_download_failed", error="file too large")
    return bytes(data)


async def download_verified_firmware(
    session: aiohttp.ClientSession, assets: dict[str, str], variant: str = "standard"
) -> bytes:
    """Download the firmware of a release and check its signature list and its SHA-256."""
    name, firmware_url, sums_url, signature_url = find_assets(assets, variant=variant)
    sums = await _download(session, sums_url, 64 * 1024)
    signature = await _download(session, signature_url, 64 * 1024)
    verify_minisign(sums, signature.decode("utf-8", "replace"))
    expected = checksum_of(sums.decode("utf-8", "replace"), name)
    firmware = await _download(session, firmware_url, MAX_FIRMWARE_BYTES)
    if expected is None or hashlib.sha256(firmware).hexdigest() != expected:
        raise OtaError("update_checksum_mismatch")
    if not firmware or firmware[0] != ESP_IMAGE_MAGIC:
        raise OtaError("update_not_a_firmware")
    return firmware


# --- the ArduinoOTA protocol ----------------------------------------------------------------------------------


def auth_response(password: str, nonce: str, file_name: str, size: int, md5: str, host: str) -> tuple[str, str]:
    """Answer to the bridge's password challenge (same computation as espota.py of the ESP32 Arduino core 3.3):
    returns (cnonce, response), both lowercase hexadecimal texts."""
    sha256_hex = lambda text: hashlib.sha256(text.encode()).hexdigest()  # noqa: E731
    cnonce = sha256_hex(f"{file_name}{size}{md5}{host}")
    password_hash = sha256_hex(password)
    key = hashlib.pbkdf2_hmac("sha256", password_hash.encode(), f"{nonce}:{cnonce}".encode(), 10_000)
    return cnonce, sha256_hex(f"{key.hex()}:{nonce}:{cnonce}")


def bare_host(host: str) -> str:
    """The name or address of the bridge without scheme, port or path."""
    host = re.sub(r"^[a-z]+://", "", host.strip().lower()).split("/")[0]
    return re.sub(r":\d+$", "", host)


@dataclass
class _Channel:
    """The UDP socket used for the invitation."""

    sock: socket.socket
    address: tuple[str, int]

    async def exchange(self, text: str, timeout: float) -> str | None:
        loop = asyncio.get_running_loop()
        await loop.sock_sendto(self.sock, text.encode(), self.address)
        try:
            async with asyncio.timeout(timeout):
                data, _ = await loop.sock_recvfrom(self.sock, 128)
        except asyncio.TimeoutError:
            return None
        return data.decode("utf-8", "replace")

    async def receive(self, timeout: float) -> str | None:
        loop = asyncio.get_running_loop()
        try:
            async with asyncio.timeout(timeout):
                data, _ = await loop.sock_recvfrom(self.sock, 128)
        except asyncio.TimeoutError:
            return None
        return data.decode("utf-8", "replace")


async def push_firmware(
    host: str,
    firmware: bytes,
    password: str | None,
    on_progress: Callable[[int], None],
    udp_port: int | None = None,
) -> None:
    """Send a firmware to the bridge. Returns when the bridge has accepted it (it then restarts)."""
    loop = asyncio.get_running_loop()
    target = bare_host(host)
    port = OTA_PORT if udp_port is None else udp_port
    try:
        infos = await loop.getaddrinfo(target, port, family=socket.AF_INET, type=socket.SOCK_DGRAM)
    except OSError as err:
        raise OtaError("update_unreachable", host=target) from err
    address = infos[0][4]

    size = len(firmware)
    md5 = hashlib.md5(firmware).hexdigest()  # noqa: S324 - the protocol asks for it

    connected: asyncio.Future[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = loop.create_future()

    def _on_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if connected.done():
            writer.close()
        else:
            connected.set_result((reader, writer))

    server = await asyncio.start_server(_on_connect, host="0.0.0.0", port=0)
    local_port = server.sockets[0].getsockname()[1]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    channel = _Channel(sock, address)
    writer: asyncio.StreamWriter | None = None
    try:
        invitation = f"0 {local_port} {size} {md5}\n"
        accepted = False
        for _ in range(INVITATION_TRIES):
            answer = await channel.exchange(invitation, INVITATION_TIMEOUT)
            if answer is None:
                continue
            if "OK" in answer:
                accepted = True
                break
            if answer.startswith("AUTH"):
                nonce = answer.split()[1] if len(answer.split()) > 1 else ""
                if not password:
                    raise OtaError("update_password_required")
                if len(nonce) != 64:
                    raise OtaError("update_auth_unsupported")
                cnonce, response = auth_response(password, nonce, "firmware.bin", size, md5, target)
                await loop.sock_sendto(sock, f"200 {cnonce} {response}\n".encode(), address)
                verdict = await channel.receive(AUTH_TIMEOUT)
                if verdict and "OK" in verdict:
                    accepted = True
                    break
                raise OtaError("update_password_wrong")
        if not accepted:
            raise OtaError("update_no_reply", host=target)

        try:
            async with asyncio.timeout(CONNECT_BACK_TIMEOUT):
                reader, writer = await connected
        except asyncio.TimeoutError:
            raise OtaError("update_no_connection", port=str(local_port)) from None

        sent = 0
        on_progress(0)
        while sent < size:
            chunk = firmware[sent : sent + CHUNK_SIZE]
            writer.write(chunk)
            try:
                async with asyncio.timeout(CHUNK_TIMEOUT):
                    await writer.drain()
                    await reader.read(32)  # the bridge acknowledges every block
            except (asyncio.TimeoutError, ConnectionError, OSError) as err:
                raise OtaError("update_transfer_failed") from err
            sent += len(chunk)
            on_progress(sent * 100 // size)

        # The bridge answers "OK" once it has checked the image, then restarts. It may restart before the answer
        # arrives: the caller then waits for the bridge to come back with the new version.
        for _ in range(10):
            try:
                async with asyncio.timeout(FINAL_TIMEOUT):
                    data = await reader.read(64)
            except (asyncio.TimeoutError, ConnectionError, OSError):
                return
            if not data or b"OK" in data:
                return
    finally:
        if writer is not None:
            writer.close()
        server.close()
        sock.close()
