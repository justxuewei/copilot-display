# copilot-display

FastAPI server that pushes text and images to a **LANCOS BluTag 4.2-inch tri-color e-ink display** (EDP-42000DDF, 400×300px, black/white/red) over BLE.

## Hardware

- **Device**: LANCOS BluTag 4.2-inch e-ink, model EDP-42000DDF
- **Resolution**: 400×300 pixels, tri-color (black / white / red)
- **BLE**: Service UUID `0000ffe0-...`, Characteristic UUID `0000ffe2-...`

## Requirements

- Python ≥ 3.9
- Linux or macOS
- Bluetooth adapter

```bash
pip install -e .
```

## Running

```bash
copilot-display
# or
python -m copilot_display.server
```

Default: `http://0.0.0.0:8420`

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `COPILOT_DISPLAY_HOST` | `0.0.0.0` | Bind address |
| `COPILOT_DISPLAY_PORT` | `8420` | Port |
| `COPILOT_DISPLAY_DEVICE_ADDRESS` | `FF:FF:42:00:11:1C` | Default BLE device MAC |
| `COPILOT_DISPLAY_API_TOKEN` | _(none)_ | If set, requests must include `X-API-Token` header |
| `COPILOT_DISPLAY_SCAN_INTERVAL` | `60` | Background scan interval (seconds) |

## API

### `GET /api/health`

```json
{"status": "ok", "version": "0.1.0", "devices": 1, "queue_depth": 0}
```

### `POST /api/push`

Push text to the display (queued).

```bash
curl -X POST http://localhost:8420/api/push \
  -H "Content-Type: application/json" \
  -d '{"body": "Hello World"}'
```

```bash
curl -X POST http://localhost:8420/api/push \
  -H "Content-Type: application/json" \
  -d '{
    "body": "Build succeeded in 42s",
    "title": "CI",
    "title_color": "red",
    "body_color": "black"
  }'
```

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `body` | string | required | Main text content |
| `title` | string | `null` | Optional title (centered, above separator) |
| `title_color` | string | `"red"` | `"red"` or `"black"` |
| `body_color` | string | `"black"` | `"red"` or `"black"` |
| `device` | string | `null` | Override BLE device address |

**Response** `202 Accepted`:
```json
{"task_id": "abc123", "status": "queued"}
```

### `POST /api/clear`

Clear the display to all-white (queued).

```bash
curl -X POST http://localhost:8420/api/clear

# Override device address
curl -X POST "http://localhost:8420/api/clear?device=FF:FF:42:00:11:1C"
```

### `GET /api/tasks/{task_id}`

Poll task status.

```bash
curl http://localhost:8420/api/tasks/abc123
```

```json
{"task_id": "abc123", "status": "done", "device": "FF:FF:42:00:11:1C", "duration_seconds": 94.2}
```

`status` values: `queued` → `in_progress` → `done` / `failed`

### `GET /api/devices`

List cached BLE devices from the last background scan.

### `POST /api/devices/scan`

Trigger an immediate BLE scan and return found devices.

## Authentication

If `COPILOT_DISPLAY_API_TOKEN` is set, all `/api/*` requests require the header:

```
X-API-Token: <token>
```

## Platform notes

| | macOS | Linux |
|---|---|---|
| BLE backend | CoreBluetooth | BlueZ |
| Protocol | cc-usage-elink V2.1 (240-byte chunks) | bbtag layer (16-byte chunks, 100ms/packet) |
| Scanner during connect | kept alive (CoreBluetooth peripheral ref) | stopped before connect (BlueZ limitation) |

The server selects the correct protocol and timing automatically.
