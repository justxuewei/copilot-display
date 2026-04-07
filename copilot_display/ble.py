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


def _address_matches(device: BLEDevice, address: str) -> bool:
    """Match a device against an address, handling macOS UUID vs MAC address formats.

    On macOS CoreBluetooth assigns UUID addresses (e.g. 815CBCE6-A8CF-...) instead
    of MAC addresses (e.g. FF:FF:42:00:11:1C). The device name encodes the last 4
    bytes of the MAC: EDP-4200111C → MAC suffix 42:00:11:1C. We use that to match.
    """
    if device.address.upper() == address.upper():
        return True
    # MAC suffix match: last 4 bytes of MAC → 8 uppercase hex chars in name
    mac_suffix = address.replace(":", "").upper()[-8:]
    return bool(mac_suffix) and mac_suffix in (device.name or "").upper()


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


async def _scan_and_connect(address: str | None, scan_timeout: float = 60.0) -> BleakClient:
    """Connect to a device, keeping the scanner alive until connect() returns.

    Strategy (mirrors cc-usage-elink find_and_connect):
    1. Fast path: if address is known, try direct connect first — CoreBluetooth
       can reconnect by address without scanning if the peripheral is cached.
    2. Scan path: start scanner, wait for device to advertise, then connect
       while the scanner is still running so CoreBluetooth retains the
       peripheral reference.
    """
    # ── Fast path: direct connect by address (no scan needed) ────────────────
    if address:
        logger.info("Trying direct connect to %s", address)
        for attempt in range(3):
            try:
                client = BleakClient(address, timeout=10.0)
                await client.connect()
                logger.info("Direct connect succeeded (attempt %d)", attempt + 1)
                return client
            except Exception as e:
                logger.debug("Direct connect attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(0.5)
        logger.info("Direct connect failed, falling back to scan")

    # ── Scan path ─────────────────────────────────────────────────────────────
    candidates: dict[str, tuple] = {}  # address -> (BLEDevice, rssi)
    ev = asyncio.Event()

    def on_detect(device: BLEDevice, adv: AdvertisementData) -> None:
        if address and not _address_matches(device, address):
            return
        if not _is_target_device(device, adv):
            return
        rssi = adv.rssi if adv.rssi is not None else -100
        prev = candidates.get(device.address)
        if prev is None or rssi > prev[1]:
            candidates[device.address] = (device, rssi)
        ev.set()

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    try:
        try:
            await asyncio.wait_for(asyncio.shield(ev.wait()), timeout=scan_timeout)
            await asyncio.sleep(3.0)  # wait for more candidates / stronger signal
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Device {address or '(any EDP)'} not found after {scan_timeout:.0f}s"
            )

        best_device, best_rssi = max(candidates.values(), key=lambda x: x[1])
        _device_cache[best_device.address] = {
            "name": best_device.name or "Unknown",
            "address": best_device.address,
        }
        logger.info(
            "Found %s (%s) RSSI=%d, connecting while scanner is alive",
            best_device.name, best_device.address, best_rssi,
        )

        # Connect with scanner still running — CoreBluetooth needs live peripheral ref
        last_exc: Exception | None = None
        for attempt in range(8):
            await asyncio.sleep(0.3)
            try:
                client = BleakClient(best_device, timeout=30.0)
                await client.connect()
                return client
            except Exception as e:
                last_exc = e
                logger.warning("Connect attempt %d/8 failed: %s", attempt + 1, e)
                if attempt < 7:
                    await asyncio.sleep(1.0)
        raise RuntimeError(
            f"Could not connect to {best_device.address} after 8 attempts: {last_exc}"
        )
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
