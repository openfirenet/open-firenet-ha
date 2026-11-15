"""Wireless update: the checks on the firmware and the ArduinoOTA protocol, against a fake bridge."""

from __future__ import annotations

import asyncio
import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from custom_components.open_firenet import ota
from custom_components.open_firenet.ota import OtaError

pytestmark = pytest.mark.usefixtures("socket_enabled")

NONCE = "272e7733cf2cf0366831fb61101a4e2911a47e5856f8b8051b576b9cc5f1e371"


def test_auth_response_matches_the_installer():
    # Same reference values as the installer's test (computed with espota.py of the ESP32 Arduino core 3.3.11).
    cnonce, response = ota.auth_response(
        "correct horse", NONCE, "fw.bin", 1_348_720, "cf3e6b8e9d1edf15458ab372b7ab5afc", "192.168.1.93"
    )
    assert cnonce == "12cf54267c312c96b01a9e22a40a213e4a4564ad12909ed0b13bdacf68d767e7"
    assert response == "716588bf93258cbea35062037d16cff0b3be156343e148341750ef7cd28cef65"


def test_bare_host():
    assert ota.bare_host("192.168.1.93") == "192.168.1.93"
    assert ota.bare_host("http://open-firenet.local:80/") == "open-firenet.local"
    assert ota.bare_host("127.0.0.1:8123") == "127.0.0.1"


def _keypair():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    key_id = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    return private, key_id, base64.b64encode(b"Ed" + key_id + raw).decode()


def _signature(private, key_id: bytes, message: bytes, algorithm: bytes = b"ED", comment: str = "file:SHA256SUMS") -> str:
    signed = hashlib.blake2b(message).digest() if algorithm == b"ED" else message
    signature = private.sign(signed)
    global_signature = private.sign(signature + comment.encode())
    return (
        "untrusted comment: signature from minisign secret key\n"
        + base64.b64encode(algorithm + key_id + signature).decode()
        + f"\ntrusted comment: {comment}\n"
        + base64.b64encode(global_signature).decode()
        + "\n"
    )


@pytest.mark.parametrize("algorithm", [b"ED", b"Ed"])
def test_valid_signature_is_accepted(algorithm):
    private, key_id, public = _keypair()
    sums = b"abc  open-firenet-ota.bin\n"
    ota.verify_minisign(sums, _signature(private, key_id, sums, algorithm), public)


def test_changed_message_is_refused():
    private, key_id, public = _keypair()
    signature = _signature(private, key_id, b"abc  open-firenet-ota.bin\n")
    with pytest.raises(OtaError) as err:
        ota.verify_minisign(b"def  open-firenet-ota.bin\n", signature, public)
    assert err.value.key == "update_signature_invalid"


def test_other_key_is_refused():
    private, key_id, _ = _keypair()
    _, _, other_public = _keypair()
    with pytest.raises(OtaError):
        ota.verify_minisign(b"x", _signature(private, key_id, b"x"), other_public)


def test_changed_trusted_comment_is_refused():
    private, key_id, public = _keypair()
    signature = _signature(private, key_id, b"x").replace("file:SHA256SUMS", "file:other")
    with pytest.raises(OtaError):
        ota.verify_minisign(b"x", signature, public)


def test_official_key_refuses_a_foreign_signature():
    private, key_id, _ = _keypair()
    with pytest.raises(OtaError):
        ota.verify_minisign(b"x", _signature(private, key_id, b"x"))


def test_checksum_of():
    sums = "AAA  open-firenet-factory.bin\nbbb *open-firenet-ota.bin\n"
    assert ota.checksum_of(sums, "open-firenet-ota.bin") == "bbb"
    assert ota.checksum_of(sums, "missing.bin") is None


def test_find_assets_needs_firmware_sums_and_signature():
    assets = {
        "open-firenet-factory.bin": "u1",
        "open-firenet-ota.bin": "u2",
        "SHA256SUMS": "u3",
        "SHA256SUMS.minisig": "u4",
    }
    assert ota.find_assets(assets) == ("open-firenet-ota.bin", "u2", "u3", "u4")
    del assets["SHA256SUMS.minisig"]
    with pytest.raises(OtaError):
        ota.find_assets(assets)


def test_find_assets_selects_variant():
    assets = {
        "open-firenet-factory.bin": "u1",
        "open-firenet-ota.bin": "u2",
        "open-firenet-factory-psram.bin": "u3",
        "open-firenet-ota-psram.bin": "u4",
        "SHA256SUMS": "u5",
        "SHA256SUMS.minisig": "u6",
    }
    assert ota.find_assets(assets, variant="standard") == ("open-firenet-ota.bin", "u2", "u5", "u6")
    assert ota.find_assets(assets, variant="psram") == ("open-firenet-ota-psram.bin", "u4", "u5", "u6")
    # Default is standard
    assert ota.find_assets(assets) == ("open-firenet-ota.bin", "u2", "u5", "u6")


def test_find_assets_psram_fallback_to_standard():
    assets = {
        "open-firenet-factory.bin": "u1",
        "open-firenet-ota.bin": "u2",
        "SHA256SUMS": "u3",
        "SHA256SUMS.minisig": "u4",
    }
    # When no PSRAM binary exists in the release, falls back to standard
    assert ota.find_assets(assets, variant="psram") == ("open-firenet-ota.bin", "u2", "u3", "u4")


class FakeEsp:
    """The update service of the bridge: UDP invitation (with an optional password), then a TCP connection back."""

    def __init__(self, password: str | None = None, ack: bool = True, verdict: str = "OK") -> None:
        self.password = password
        self.ack = ack
        self.verdict = verdict
        self.received = b""
        self.port = 0
        self.done = asyncio.Event()
        self._transport = None
        self._invitation: tuple[str, int, int, str] | None = None
        self._peer = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(lambda: self, local_addr=("127.0.0.1", 0))
        self.port = self._transport.get_extra_info("sockname")[1]

    def stop(self) -> None:
        self._transport.close()

    # datagram protocol
    def connection_made(self, transport) -> None:
        pass

    def datagram_received(self, data: bytes, addr) -> None:
        parts = data.decode().split()
        if parts[0] == "0":
            self._peer = addr
            self._invitation = (addr[0], int(parts[1]), int(parts[2]), parts[3])
            if self.password is None:
                self._transport.sendto(b"OK", addr)
                asyncio.get_running_loop().create_task(self._receive())
            else:
                self._transport.sendto(f"AUTH {NONCE}".encode(), addr)
        elif parts[0] == "200":
            cnonce, response = parts[1], parts[2]
            password_hash = hashlib.sha256(self.password.encode()).hexdigest()
            key = hashlib.pbkdf2_hmac("sha256", password_hash.encode(), f"{NONCE}:{cnonce}".encode(), 10_000)
            expected = hashlib.sha256(f"{key.hex()}:{NONCE}:{cnonce}".encode()).hexdigest()
            if response == expected:
                self._transport.sendto(b"OK", addr)
                asyncio.get_running_loop().create_task(self._receive())
            else:
                self._transport.sendto(b"Authentication Failed", addr)

    def error_received(self, exc) -> None:
        pass

    def connection_lost(self, exc) -> None:
        pass

    async def _receive(self) -> None:
        _, port, size, _ = self._invitation
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        while len(self.received) < size:
            chunk = await reader.read(2048)
            if not chunk:
                break
            self.received += chunk
            if self.ack:
                writer.write(str(len(chunk)).encode())
                await writer.drain()
        writer.write(self.verdict.encode())
        await writer.drain()
        writer.close()
        self.done.set()


@pytest.fixture
async def esp():
    fake = FakeEsp()
    await fake.start()
    yield fake
    fake.stop()


FIRMWARE = bytes([0xE9]) + bytes(range(256)) * 20  # 5121 bytes, 6 blocks


async def test_firmware_is_sent_whole(esp):
    progress: list[int] = []
    await ota.push_firmware("127.0.0.1:80", FIRMWARE, None, progress.append, udp_port=esp.port)
    assert esp.received == FIRMWARE
    assert progress[-1] == 100


async def test_password_is_answered():
    esp = FakeEsp(password="correct horse")
    await esp.start()
    try:
        await ota.push_firmware("127.0.0.1", FIRMWARE, "correct horse", lambda p: None, udp_port=esp.port)
        assert esp.received == FIRMWARE
    finally:
        esp.stop()


async def test_wrong_password_sends_nothing():
    esp = FakeEsp(password="correct horse")
    await esp.start()
    try:
        with pytest.raises(OtaError) as err:
            await ota.push_firmware("127.0.0.1", FIRMWARE, "wrong", lambda p: None, udp_port=esp.port)
        assert err.value.key == "update_password_wrong"
        assert esp.received == b""
    finally:
        esp.stop()


async def test_missing_password_is_asked_for():
    esp = FakeEsp(password="correct horse")
    await esp.start()
    try:
        with pytest.raises(OtaError) as err:
            await ota.push_firmware("127.0.0.1", FIRMWARE, None, lambda p: None, udp_port=esp.port)
        assert err.value.key == "update_password_required"
    finally:
        esp.stop()


async def test_silent_bridge(monkeypatch):
    monkeypatch.setattr(ota, "INVITATION_TRIES", 2)
    monkeypatch.setattr(ota, "INVITATION_TIMEOUT", 0.05)
    # A port nobody listens on.
    with pytest.raises(OtaError) as err:
        await ota.push_firmware("127.0.0.1", FIRMWARE, None, lambda p: None, udp_port=9)
    assert err.value.key == "update_no_reply"


async def test_download_reads_a_whole_file_sent_in_pieces():
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    import aiohttp

    body = bytes(range(256)) * 2000  # 512000 bytes, sent in several writes

    async def handler(request):
        resp = web.StreamResponse()
        await resp.prepare(request)
        for start in range(0, len(body), 30000):
            await resp.write(body[start : start + 30000])
            await asyncio.sleep(0)
        return resp

    app = web.Application()
    app.router.add_get("/f", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        async with aiohttp.ClientSession() as session:
            assert await ota._download(session, str(server.make_url("/f")), 4 * 1024 * 1024) == body
            with pytest.raises(OtaError):
                await ota._download(session, str(server.make_url("/f")), 1000)
    finally:
        await server.close()
