"""BLE communication for the 4.2-inch LANCOS BluTag e-ink display."""

from __future__ import annotations

import asyncio
import logging
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from PIL import Image

logger = logging.getLogger(__name__)

# BLE constants
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

# Channel types
TYPE_BLACK = 0x13
TYPE_RED = 0x12

# Screen dimensions
SCREEN_W = 400
SCREEN_H = 300

# Max payload per BLE data packet
CHUNK_SIZE = 240

# Device cache
_device_cache: dict[str, dict] = {}
_cache_lock = asyncio.Lock()

# Push lock — only one BLE transmission at a time
_push_lock = asyncio.Lock()


def image_to_channels(img: Image.Image) -> tuple[bytes, bytes]:
    """Convert a PIL Image to black and red channel bytes for the 4.2" display.

    Returns (black_bytes, red_bytes).
    """
    img = img.convert("RGB").resize((SCREEN_W, SCREEN_H))
    pixels = img.load()

    black_data = bytearray()
    red_data = bytearray()

    # Scan bottom-to-top
    for y in range(SCREEN_H - 1, -1, -1):
        for x_byte in range(SCREEN_W // 8):
            black_byte = 0
            red_byte = 0
            for bit in range(8):
                x = x_byte * 8 + bit
                r, g, b = pixels[x, y]

                is_red = r > 150 and g < 100 and b < 100
                is_black = (r + g + b) < 200 and not is_red

                # Black channel: bit=1 for white, bit=0 for black
                if not is_black:
                    black_byte |= 1 << (7 - bit)

                # Red channel: bit=1 for red
                if is_red:
                    red_byte |= 1 << (7 - bit)

            black_data.append(black_byte)
            red_data.append(red_byte)

    return bytes(black_data), bytes(red_data)


def _build_start(channel_type: int) -> bytes:
    return bytes([channel_type, 0x00, 0x00])


def _build_end(channel_type: int) -> bytes:
    return bytes([channel_type, 0xFF, 0xFF])


def _build_data_packets(channel_type: int, data: bytes) -> list[bytes]:
    packets = []
    offset = 0
    while offset < len(data):
        chunk = data[offset : offset + CHUNK_SIZE]
        hi = (offset >> 8) & 0xFF
        lo = offset & 0xFF
        packet = bytes([channel_type, hi, lo, len(chunk)]) + chunk
        packets.append(packet)
        offset += len(chunk)
    return packets


async def _send_channel(
    client: BleakClient,
    channel_type: int,
    data: bytes,
    on_progress: callable | None = None,
) -> None:
    """Send one color channel to the device with required timing."""
    channel_name = "black" if channel_type == TYPE_BLACK else "red"
    logger.info("Sending %s channel (%d bytes)", channel_name, len(data))

    packets = _build_data_packets(channel_type, data)
    total = len(packets)

    # Start
    await client.write_gatt_char(CHAR_UUID, _build_start(channel_type), response=False)
    await asyncio.sleep(3.0)

    # Data packets
    for i, packet in enumerate(packets):
        await client.write_gatt_char(CHAR_UUID, packet, response=False)
        delay = 1.0 if i < 10 else 0.6
        await asyncio.sleep(delay)
        if on_progress:
            on_progress(channel_name, i + 1, total)

    # End
    await client.write_gatt_char(CHAR_UUID, _build_end(channel_type), response=False)
    await asyncio.sleep(0.1)

    logger.info("Finished %s channel", channel_name)


def _is_target_device(device: BLEDevice, adv: AdvertisementData) -> bool:
    if device.name and "EDP" in device.name.upper():
        return True
    if SERVICE_UUID in [str(u) for u in (adv.service_uuids or [])]:
        return True
    return False


async def scan_devices(timeout: float = 8.0) -> list[dict]:
    """Scan for BluTag 4.2-inch devices."""
    found: dict[str, dict] = {}

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        if _is_target_device(device, adv):
            found[device.address] = {
                "name": device.name or "Unknown",
                "address": device.address,
                "rssi": adv.rssi,
            }

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    devices = sorted(found.values(), key=lambda d: d.get("rssi") or -999, reverse=True)

    # Update cache
    async with _cache_lock:
        _device_cache.clear()
        for d in devices:
            _device_cache[d["address"]] = d

    logger.info("Scan found %d device(s)", len(devices))
    return devices


def get_cached_devices() -> list[dict]:
    return list(_device_cache.values())


async def push_image(
    img: Image.Image,
    device_address: str | None = None,
    on_progress: callable | None = None,
) -> dict:
    """Push an image to the 4.2-inch e-ink display.

    Returns a dict with status and timing info.
    """
    if _push_lock.locked():
        raise RuntimeError("Another push is already in progress")

    async with _push_lock:
        black_data, red_data = image_to_channels(img)
        start_time = time.monotonic()

        # Resolve device
        address = device_address
        if not address:
            devices = get_cached_devices()
            if not devices:
                logger.info("No cached devices, scanning...")
                devices = await scan_devices(timeout=10.0)
            if not devices:
                raise RuntimeError("No BluTag devices found")
            address = devices[0]["address"]

        logger.info("Connecting to %s", address)

        async with BleakClient(address, timeout=20.0) as client:
            if not client.is_connected:
                raise RuntimeError(f"Failed to connect to {address}")

            logger.info("Connected, starting transmission")
            await _send_channel(client, TYPE_BLACK, black_data, on_progress)
            await _send_channel(client, TYPE_RED, red_data, on_progress)

        elapsed = time.monotonic() - start_time
        logger.info("Push complete in %.1fs", elapsed)
        return {
            "status": "ok",
            "device": address,
            "duration_seconds": round(elapsed, 1),
        }
