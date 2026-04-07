"""BLE communication for the 4.2-inch LANCOS BluTag e-ink display."""

from __future__ import annotations

import asyncio
import logging
import math
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

# Max payload per BLE data packet (bbtag layer protocol uses 16 for EDP- devices)
LAYER_PAYLOAD_SIZE = 16
DELAY_MS = 100

# Device cache
_device_cache: dict[str, dict] = {}

# Single lock for ALL BLE radio operations.
# BlueZ cannot scan and connect concurrently — one lock prevents both races.
_ble_lock = asyncio.Lock()


def image_to_channels(img: Image.Image) -> tuple[bytes, bytes]:
    """Convert a PIL Image to black and red channel bytes for the 4.2" display."""
    img = img.convert("RGB").resize((SCREEN_W, SCREEN_H), Image.LANCZOS)
    pixels = img.load()

    black_data = bytearray()
    red_data = bytearray()

    # Scan bottom-to-top
    for y in range(SCREEN_H - 1, -1, -1):
        for x_byte in range(math.ceil(SCREEN_W / 8)):
            black_byte = 0
            red_byte = 0
            for bit in range(8):
                x = x_byte * 8 + bit
                if x >= SCREEN_W:
                    black_byte |= 1 << (7 - bit)  # pad with white
                    continue
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


async def _send_channel(
    client: BleakClient,
    channel_type: int,
    data: bytes,
    on_progress: callable | None = None,
) -> None:
    """Send one color channel using the bbtag EDP- layer protocol."""
    channel_name = "black" if channel_type == TYPE_BLACK else "red"
    delay = DELAY_MS / 1000.0
    total_packets = math.ceil(len(data) / LAYER_PAYLOAD_SIZE)
    logger.info("Sending %s channel (%d bytes, %d packets)", channel_name, len(data), total_packets)

    # Start packet: [type, 0x00, 0x00, 0x00, 0x00]
    await client.write_gatt_char(CHAR_UUID, bytes([channel_type, 0x00, 0x00, 0x00, 0x00]), response=False)
    await asyncio.sleep(delay)
    await asyncio.sleep(1.0)  # extra settle after start

    first_sent = False
    packet_index = 1
    offset = 0
    while offset < len(data):
        chunk = data[offset : offset + LAYER_PAYLOAD_SIZE]
        packet = bytes([channel_type, packet_index & 0xFF, len(chunk)]) + chunk
        await client.write_gatt_char(CHAR_UUID, packet, response=False)
        if not first_sent:
            await asyncio.sleep(delay)
            await client.write_gatt_char(CHAR_UUID, packet, response=False)  # send first pkt twice
            first_sent = True
        await asyncio.sleep(delay)
        if on_progress:
            on_progress(channel_name, packet_index, total_packets)
        offset += len(chunk)
        packet_index += 1

    # End packet: [type, 0xFF, 0xFF, 0xFF, 0xFF]
    await client.write_gatt_char(CHAR_UUID, bytes([channel_type, 0xFF, 0xFF, 0xFF, 0xFF]), response=False)
    await asyncio.sleep(delay)

    logger.info("Finished %s channel", channel_name)


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
                "name": device.name or "Unknown",
                "address": device.address,
                "rssi": adv.rssi,
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


async def _scan_and_connect(address: str | None, scan_timeout: float = 15.0) -> BleakClient:
    """Scan for a device and connect while the scanner is still running.

    CoreBluetooth (macOS) loses the peripheral reference as soon as the scanner
    stops, so connecting after stop always raises BleakDeviceNotFoundError.
    Keeping the scanner alive until connect() returns fixes this.
    """
    found: BLEDevice | None = None
    ev = asyncio.Event()

    def on_detect(device: BLEDevice, adv: AdvertisementData) -> None:
        nonlocal found
        if address:
            if device.address == address:
                found = device
                ev.set()
        elif _is_target_device(device, adv):
            found = device
            ev.set()

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    try:
        try:
            await asyncio.wait_for(ev.wait(), timeout=scan_timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Device {address or '(any EDP)'} not found after {scan_timeout:.0f}s"
            )

        _device_cache[found.address] = {"name": found.name or "Unknown", "address": found.address}
        logger.info("Found %s (%s), connecting while scanner is alive", found.name, found.address)

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                client = BleakClient(found, timeout=30.0)
                await client.connect()
                return client
            except Exception as e:
                last_exc = e
                logger.warning("Connect attempt %d/3 failed: %s", attempt, e)
                if attempt < 3:
                    await asyncio.sleep(1.0)
        raise RuntimeError(f"Could not connect to {found.address} after 3 attempts: {last_exc}")
    finally:
        await scanner.stop()


async def scan_devices(timeout: float = 8.0) -> list[dict]:
    """Scan for BluTag devices. Skips silently if BLE radio is busy."""
    if _ble_lock.locked():
        logger.debug("BLE radio busy, skipping background scan")
        return list(_device_cache.values())

    async with _ble_lock:
        return await _do_scan(timeout)


def get_cached_devices() -> list[dict]:
    return list(_device_cache.values())


async def clear_display(device_address: str | None = None) -> dict:
    """Send all-white image to clear the display."""
    white = Image.new("RGB", (SCREEN_W, SCREEN_H), (255, 255, 255))
    return await push_image(white, device_address=device_address)


async def push_image(
    img: Image.Image,
    device_address: str | None = None,
    on_progress: callable | None = None,
) -> dict:
    """Push an image to the 4.2-inch e-ink display."""
    # Wait for the lock — background scan may be holding it briefly (up to ~10s)
    async with _ble_lock:
        img.save("/tmp/copilot_display_last.png")
        logger.info("Saved render to /tmp/copilot_display_last.png")
        black_data, red_data = image_to_channels(img)
        logger.info("Encoded: black[0:4]=%s red[0:4]=%s", black_data[:4].hex(), red_data[:4].hex())
        start_time = time.monotonic()

        # _scan_and_connect keeps the scanner alive until connect() returns,
        # which is required on CoreBluetooth (macOS) to retain the peripheral ref.
        client = await _scan_and_connect(device_address)
        try:
            await asyncio.sleep(1.0)  # let GATT services settle

            # Negotiate MTU — bleak on BlueZ doesn't do this automatically
            try:
                await client._backend._acquire_mtu()
            except Exception as e:
                logger.warning("MTU negotiation failed: %s", e)

            logger.info("Connected, MTU=%d, starting transmission", client.mtu_size)
            await _send_channel(client, TYPE_BLACK, black_data, on_progress)
            await _send_channel(client, TYPE_RED, red_data, on_progress)
        finally:
            await client.disconnect()

        elapsed = time.monotonic() - start_time
        logger.info("Push complete in %.1fs", elapsed)
        return {
            "status": "ok",
            "device": address,
            "duration_seconds": round(elapsed, 1),
        }
