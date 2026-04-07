"""BLE communication for the 4.2-inch LANCOS BluTag e-ink display.

Protocol and connection logic ported from cc-usage-elink (elink.py).
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from PIL import Image

logger = logging.getLogger(__name__)

# BLE constants
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID    = "0000ffe2-0000-1000-8000-00805f9b34fb"

# Channel types
TYPE_BLACK = 0x13  # bit=1 → white, bit=0 → black
TYPE_RED   = 0x12  # bit=1 → red

# Screen dimensions
SCREEN_W = 400
SCREEN_H = 300

# Platform-specific transmission parameters.
#
# macOS CoreBluetooth auto-negotiates a large ATT_MTU (~512 bytes), so 240-byte
# chunks (244 bytes on the wire) fit fine and cc-usage-elink timing works.
#
# Linux BlueZ defaults to ATT_MTU=23. A 244-byte write silently truncates to 20
# bytes (ATT_MTU − 3 for WoR), corrupting every packet → noise pixels.
# bbtag uses 16-byte chunks at 100 ms (its confirmed-working 4.2-inch profile)
# which stays safely within the 20-byte payload limit.
if sys.platform == "linux":
    CHUNK       = 16    # bbtag 4.2inch: LAYER_PAYLOAD_SIZE=16
    _DELAY_MS   = 100   # bbtag 4.2inch: default_interval_ms=100
    _DOUBLE_FIRST = True  # bbtag quirk: send first data packet twice
else:
    CHUNK       = 240   # cc-usage-elink V2.1
    _DELAY_MS   = None  # use cc-usage-elink variable timing (1s/0.6s)
    _DOUBLE_FIRST = False

# Device cache
_device_cache: dict[str, dict] = {}

# Single lock for all BLE radio ops (BlueZ cannot scan+connect concurrently)
_ble_lock = asyncio.Lock()


# ── Protocol ──────────────────────────────────────────────────────────────────

def _build_start(color_type: int) -> bytes:
    return bytes([color_type, 0x00, 0x00])


def _build_end(color_type: int) -> bytes:
    return bytes([color_type, 0xFF, 0xFF])


def _build_data_packets(color_type: int, data: bytes) -> list[bytes]:
    packets = []
    for i, offset in enumerate(range(0, len(data), CHUNK)):
        idx   = i + 1
        chunk = data[offset : offset + CHUNK]
        hi    = (idx >> 8) & 0xFF
        lo    = idx & 0xFF
        packets.append(bytes([color_type, hi, lo, len(chunk)]) + chunk)
    return packets


# ── Image encoding ────────────────────────────────────────────────────────────

def image_to_channels(img: Image.Image) -> tuple[bytes, bytes]:
    """Convert a PIL Image to (black_bytes, red_bytes) for the 4.2" display."""
    img = img.convert("RGB").resize((SCREEN_W, SCREEN_H))
    black_data = bytearray()
    red_data   = bytearray()

    for y in range(SCREEN_H - 1, -1, -1):
        for byte_idx in range(math.ceil(SCREEN_W / 8)):
            b_black = 0
            b_red   = 0
            for bit in range(8):
                x = byte_idx * 8 + bit
                if x >= SCREEN_W:
                    b_black |= 1 << (7 - bit)  # pad with white
                    continue
                r, g, b = img.getpixel((x, y))
                is_red   = r > 150 and g < 100 and b < 100
                is_black = (r + g + b) < 200 and not is_red
                if not is_black:
                    b_black |= 1 << (7 - bit)
                if is_red:
                    b_red |= 1 << (7 - bit)
            black_data.append(b_black)
            red_data.append(b_red)

    return bytes(black_data), bytes(red_data)


# ── Send ──────────────────────────────────────────────────────────────────────

async def _send_channel(
    client: BleakClient,
    color_type: int,
    data: bytes,
    on_progress: callable | None = None,
) -> None:
    """Send one color channel.

    macOS: cc-usage-elink V2.1 timing (1s/0.6s, 240-byte chunks).
    Linux: bbtag 4.2inch profile (100ms, 16-byte chunks, double first packet).
    """
    name    = "black" if color_type == TYPE_BLACK else "red"
    packets = _build_data_packets(color_type, data)
    logger.info("Sending %s channel (%d bytes, %d packets)", name, len(data), len(packets))

    await client.write_gatt_char(CHAR_UUID, _build_start(color_type), response=False)
    await asyncio.sleep(3.0)  # device init after start

    first_sent = False
    for i, pkt in enumerate(packets):
        await client.write_gatt_char(CHAR_UUID, pkt, response=False)

        if _DOUBLE_FIRST and not first_sent:
            delay = _DELAY_MS / 1000.0
            await asyncio.sleep(delay)
            await client.write_gatt_char(CHAR_UUID, pkt, response=False)  # bbtag: send first pkt twice
            first_sent = True

        if _DELAY_MS is not None:
            await asyncio.sleep(_DELAY_MS / 1000.0)
        else:
            await asyncio.sleep(1.0 if i < 10 else 0.6)

        if on_progress:
            on_progress(name, i + 1, len(packets))

    await client.write_gatt_char(CHAR_UUID, _build_end(color_type), response=False)
    await asyncio.sleep(0.1)
    logger.info("Finished %s channel", name)


# ── Device detection ──────────────────────────────────────────────────────────

def _is_target_device(device: BLEDevice, adv: AdvertisementData) -> bool:
    name  = (device.name or "").upper()
    uuids = " ".join(str(u).lower() for u in (adv.service_uuids or []))
    return "EDP" in name or SERVICE_UUID.lower() in uuids


def _address_matches(device: BLEDevice, address: str) -> bool:
    """Match a device against an address across macOS UUID and Linux MAC formats.

    CoreBluetooth (macOS) uses UUID addresses (e.g. 815CBCE6-A8CF-...) while
    Linux BlueZ uses MAC addresses (e.g. FF:FF:42:00:11:1C). The device name
    encodes the last 4 MAC bytes: EDP-4200111C → MAC suffix 4200111C.
    """
    if device.address.upper() == address.upper():
        return True
    mac_suffix = address.replace(":", "").upper()[-8:]
    return bool(mac_suffix) and mac_suffix in (device.name or "").upper()


# ── Scan / connect ────────────────────────────────────────────────────────────

async def _do_scan(timeout: float) -> list[dict]:
    """Inner scan — caller must hold _ble_lock."""
    found: dict[str, dict] = {}

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        if _is_target_device(device, adv):
            found[device.address] = {
                "name":    device.name or "Unknown",
                "address": device.address,
                "rssi":    adv.rssi,
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


async def _find_and_connect(address: str | None, scan_timeout: float = 60.0) -> BleakClient:
    """Scan for a device then connect while the scanner is still running.

    CoreBluetooth (macOS) loses the peripheral reference as soon as the scanner
    stops. Keeping it alive until connect() returns preserves the reference.
    Mirrors cc-usage-elink find_and_connect (scan path only).
    """
    candidates: dict[str, tuple] = {}  # device.address -> (BLEDevice, rssi)
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
        if not ev.is_set():
            ev.set()

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()

    try:
        await asyncio.wait_for(asyncio.shield(ev.wait()), timeout=scan_timeout)
        await asyncio.sleep(3.0)  # collect more candidates, pick best RSSI
    except asyncio.TimeoutError:
        await scanner.stop()
        raise RuntimeError(
            f"Device {address or '(any EDP)'} not found after {scan_timeout:.0f}s"
        )

    best_device, best_rssi = max(candidates.values(), key=lambda x: x[1])
    _device_cache[best_device.address] = {
        "name": best_device.name or "Unknown", "address": best_device.address,
    }
    logger.info(
        "Found %s (%s) RSSI=%d, connecting while scanner is alive",
        best_device.name, best_device.address, best_rssi,
    )

    # On Linux/BlueZ, use the address string rather than the BLEDevice object.
    # After a connect() timeout BlueZ leaves a stale connection entry; calling
    # disconnect() explicitly clears it before retrying.
    device_ref = best_device.address if sys.platform == "linux" else best_device

    for attempt in range(8):
        await asyncio.sleep(0.3)
        client = BleakClient(device_ref, timeout=30.0)
        try:
            await client.connect()
            await scanner.stop()
            return client
        except Exception as e:
            logger.warning("Connect attempt %d/8 failed: %s", attempt + 1, e)
            try:
                await client.disconnect()  # clear stale BlueZ state
            except Exception:
                pass
            if attempt < 7:
                await asyncio.sleep(2.0)  # give BlueZ time to recover

    await scanner.stop()
    raise RuntimeError(f"Could not connect to {best_device.address} after 8 attempts")


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

async def clear_display(device_address: str | None = None) -> dict:
    """Send all-white image to clear the display."""
    white = Image.new("RGB", (SCREEN_W, SCREEN_H), (255, 255, 255))
    return await push_image(white, device_address=device_address)


async def push_image(
    img: Image.Image,
    device_address: str | None = None,
    on_progress: callable | None = None,
) -> dict:
    """Push a PIL Image to the 4.2-inch e-ink display."""
    async with _ble_lock:
        img.save("/tmp/copilot_display_last.png")
        logger.info("Saved render to /tmp/copilot_display_last.png")

        black_data, red_data = image_to_channels(img)
        logger.info(
            "Encoded: black[0:4]=%s red[0:4]=%s",
            black_data[:4].hex(), red_data[:4].hex(),
        )
        start_time = time.monotonic()

        client = await _find_and_connect(device_address)
        try:
            await _send_channel(client, TYPE_BLACK, black_data, on_progress)
            await _send_channel(client, TYPE_RED,   red_data,   on_progress)
        finally:
            await client.disconnect()

        elapsed = time.monotonic() - start_time
        logger.info("Push complete in %.1fs", elapsed)
        return {
            "status": "ok",
            "device": device_address,
            "duration_seconds": round(elapsed, 1),
        }
