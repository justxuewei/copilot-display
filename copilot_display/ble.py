"""BLE communication for the 4.2-inch LANCOS BluTag e-ink display.

Protocol ported from bbtag (bluetag/transfer.py + bluetag/ble.py) for EDP- devices.
"""

from __future__ import annotations

import asyncio
import logging
import time

import numpy as np
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from PIL import Image

logger = logging.getLogger(__name__)

# BLE constants
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID    = "0000ffe2-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID  = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Channel types (bbtag: BLACK_TYPE / RED_TYPE)
TYPE_BLACK = 0x13
TYPE_RED   = 0x12

# Screen dimensions
SCREEN_W = 400
SCREEN_H = 300

# Transmission parameters (from bbtag 2.13inch profile)
LAYER_PAYLOAD_SIZE = 16   # bytes per data packet
DELAY_MS           = 100  # ms between packets
SETTLE_MS          = 1500 # ms to wait after both channels are sent

# Device cache
_device_cache: dict[str, dict] = {}

# Single lock for all BLE radio ops (BlueZ can't scan+connect concurrently)
_ble_lock = asyncio.Lock()


# ── Image encoding ────────────────────────────────────────────────────────────

def image_to_black_channel(img: Image.Image) -> bytes:
    """Convert PIL Image to black channel bytes (bbtag layer_to_bytes_rowwise)."""
    img = img.convert("RGB").resize((SCREEN_W, SCREEN_H), Image.LANCZOS)
    gray = np.array(img, dtype=np.uint8).mean(axis=2)
    # black_layer: 1 = light (white), 0 = dark (black) — bit=1 → white in protocol
    black_layer = (gray >= 128).astype(np.uint8)
    return _layer_to_bytes(black_layer)


def _layer_to_bytes(layer: np.ndarray) -> bytes:
    """Pack a binary layer row-by-row, 8 horizontal pixels per byte (bbtag rowwise)."""
    height, width = layer.shape
    bytes_per_row = (width + 7) // 8
    data = []
    for row in range(height):
        for byte_idx in range(bytes_per_row):
            byte_val = 0
            for bit_idx in range(8):
                col = byte_idx * 8 + (7 - bit_idx)
                if col < width and layer[row, col]:
                    byte_val |= 1 << bit_idx
            data.append(byte_val)
    return bytes(data)


# ── BLE session ───────────────────────────────────────────────────────────────

class _BleSession:
    """Thin BLE session wrapper (ported from bbtag BleSession)."""

    def __init__(self, client: BleakClient):
        self._client = client

    async def write(self, data: bytes) -> None:
        await self._client.write_gatt_char(CHAR_UUID, data, response=False)

    async def flush(self) -> None:
        try:
            await self._client.read_gatt_char(NOTIFY_UUID)
        except Exception:
            pass

    async def close(self) -> None:
        if self._client.is_connected:
            await self._client.disconnect()


async def _open_session(address: str, timeout: float = 30.0) -> _BleSession:
    """Connect and return a ready BLE session (bbtag BleSession.open pattern)."""
    client = BleakClient(address, timeout=timeout)
    await client.connect()
    await asyncio.sleep(1.0)  # let GATT services settle (bbtag pattern)

    # Subscribe to notifications — device may require this before accepting writes
    try:
        await client.start_notify(NOTIFY_UUID, lambda _s, _d: None)
    except Exception:
        pass

    return _BleSession(client)


# ── Layer transmission ────────────────────────────────────────────────────────

async def _send_layer(
    session: _BleSession,
    channel_type: int,
    data: bytes,
    on_progress: callable | None,
) -> None:
    """Send one color layer (exact copy of bbtag _send_layer)."""
    name  = "black" if channel_type == TYPE_BLACK else "red"
    delay = DELAY_MS / 1000.0
    total = (len(data) + LAYER_PAYLOAD_SIZE - 1) // LAYER_PAYLOAD_SIZE
    logger.info("Sending %s layer (%d bytes, %d packets)", name, len(data), total)

    # Start: [type, 0x00, 0x00, 0x00, 0x00]
    await session.write(bytes([channel_type, 0x00, 0x00, 0x00, 0x00]))
    await asyncio.sleep(delay)
    await asyncio.sleep(1.0)  # extra settle after start

    first_sent = False
    packet_index = 1
    offset = 0
    while offset < len(data):
        chunk  = data[offset : offset + LAYER_PAYLOAD_SIZE]
        packet = bytes([channel_type, packet_index & 0xFF, len(chunk)]) + chunk

        await session.write(packet)
        if not first_sent:
            await asyncio.sleep(delay)
            await session.write(packet)  # first packet sent twice (bbtag quirk)
            first_sent = True

        await asyncio.sleep(delay)
        if on_progress:
            on_progress(name, packet_index, total)
        offset += len(chunk)
        packet_index += 1

    # End: [type, 0xFF, 0xFF, 0xFF, 0xFF]
    await session.write(bytes([channel_type, 0xFF, 0xFF, 0xFF, 0xFF]))
    await asyncio.sleep(delay)
    logger.info("Finished %s layer", name)


# ── Scan / device cache ───────────────────────────────────────────────────────

def _is_target_device(device: BLEDevice, adv: AdvertisementData) -> bool:
    if device.name and "EDP" in device.name.upper():
        return True
    if SERVICE_UUID in [str(u) for u in (adv.service_uuids or [])]:
        return True
    return False


async def _do_scan(timeout: float) -> list[dict]:
    """Inner scan — caller must hold _ble_lock."""
    found: dict[str, dict] = {}

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        if _is_target_device(device, adv):
            found[device.address] = {
                "name":    device.name or "Unknown",
                "address": device.address,
                "rssi":    adv.rssi,
                "_device": device,
            }

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    devices = sorted(found.values(), key=lambda d: d.get("rssi") or -999, reverse=True)
    _device_cache.clear()
    for d in devices:
        _device_cache[d["address"]] = d

    logger.info("Scan found %d device(s)", len(devices))
    for d in devices:
        logger.info("  Device: %s  addr=%s  rssi=%s", d["name"], d["address"], d.get("rssi"))
    return devices


async def scan_devices(timeout: float = 8.0) -> list[dict]:
    """Scan for BluTag devices. Skips silently if BLE radio is busy."""
    if _ble_lock.locked():
        logger.debug("BLE radio busy, skipping background scan")
        return list(_device_cache.values())
    async with _ble_lock:
        return await _do_scan(timeout)


def get_cached_devices() -> list[dict]:
    return list(_device_cache.values())


# ── Public API ────────────────────────────────────────────────────────────────

async def push_image(
    img: Image.Image,
    device_address: str | None = None,
    on_progress: callable | None = None,
) -> dict:
    """Push a PIL Image to the 4.2-inch e-ink display."""
    async with _ble_lock:
        img.save("/tmp/copilot_display_last.png")
        logger.info("Saved render to /tmp/copilot_display_last.png")

        black_data = image_to_black_channel(img)
        logger.info("Encoded: black[0:4]=%s total=%d bytes", black_data[:4].hex(), len(black_data))
        start_time = time.monotonic()

        # Resolve address
        address = device_address
        if not address:
            devices = get_cached_devices()
            if not devices:
                logger.info("No cached devices, scanning...")
                devices = await _do_scan(timeout=10.0)
            if not devices:
                raise RuntimeError("No BluTag devices found")
            address = devices[0]["address"]

        logger.info("Connecting to %s", address)

        max_retries = 5
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            session: _BleSession | None = None
            try:
                session = await _open_session(address)
                logger.info("Connected to %s (attempt %d)", address, attempt)
                await _send_layer(session, TYPE_BLACK, black_data, on_progress)
                await asyncio.sleep(SETTLE_MS / 1000.0)
                break
            except (TimeoutError, asyncio.TimeoutError, OSError) as e:
                last_exc = e
                logger.warning("Connection attempt %d/%d failed: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(3.0)
            finally:
                if session:
                    await session.close()
        else:
            raise RuntimeError(
                f"Could not connect to {address} after {max_retries} attempts: {last_exc}"
            )

        elapsed = time.monotonic() - start_time
        logger.info("Push complete in %.1fs", elapsed)
        return {"status": "ok", "device": address, "duration_seconds": round(elapsed, 1)}
