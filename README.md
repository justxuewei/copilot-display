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

### Locally

```bash
copilot-display
# or
python -m copilot_display.server
```

Default: `http://0.0.0.0:8420`

Open `http://localhost:8420` in a browser for the web UI.

### Using Docker

You can run the server via Docker. The container uses the `/etc/codisplay` volume for persistent configuration and state files.

Because the Python application communicates with the host's Bluetooth Low Energy stack (`BlueZ`), the container must have access to the host's `dbus` socket to function:

```bash
docker run -d \
  --name copilot-display \
  --security-opt apparmor=unconfined \
  --cap-add=NET_ADMIN \
  -p 8420:8420 \
  -v /var/run/dbus:/var/run/dbus \
  -v codisplay_data:/etc/codisplay \
  xavierniu/copilot-display
```

> **Note on Bluetooth Permissions:** Depending on your Linux distribution's `BlueZ` configuration, Docker's default security profiles can block D-Bus messages. 
> - If you encounter `BleakDBusError: ... An AppArmor policy prevents...` errors, be sure to use `--security-opt apparmor=unconfined` to bypass the AppArmor D-Bus restrictions.
> - If you encounter other BLE discovery or connection errors, you may need to grant `--cap-add=NET_ADMIN` or default to host networking (`--network host` instead of `-p 8420:8420`).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `COPILOT_DISPLAY_HOST` | `0.0.0.0` | Bind address |
| `COPILOT_DISPLAY_PORT` | `8420` | Port |
| `COPILOT_DISPLAY_DEVICE_ADDRESS` | `FF:FF:42:00:11:1C` | Default BLE device MAC |
| `COPILOT_DISPLAY_API_TOKEN` | _(none)_ | If set, requests must include `X-API-Token` header |
| `COPILOT_DISPLAY_SCAN_INTERVAL` | `60` | Background BLE scan interval (seconds) |
| `COPILOT_DISPLAY_DATA_DIR` | `/etc/codisplay` | Directory for config, device cache, and state files |

### Configuration file

On first run the server writes `/etc/codisplay/config.json` with defaults:

```json
{
  "scan_interval": 60,
  "refresh_interval": 300,
  "work_days": [0, 1, 2, 3, 4],
  "work_start": "10:00",
  "work_end": "20:00",
  "template": "",
  "template_data": {}
}
```

| Key | Description |
|---|---|
| `scan_interval` | Seconds between background BLE scans (`0` = disabled) |
| `refresh_interval` | Seconds between automatic display refreshes (`0` = disabled) |
| `work_days` | Days to allow refresh: `0`=Mon … `6`=Sun. Empty list = every day |
| `work_start` / `work_end` | Active time window as `HH:MM`. Empty strings = always active |
| `template` | Template name to render on each refresh (e.g. `"stock"`) |
| `template_data` | Data passed to the template's `fetch()` on each refresh |

## Templates

### `stock` — Live stock watchlist

Renders a monospace box-drawing watchlist using live data from Yahoo Finance.

```
┌──────────────────────────────────────┐
│ Copilot Display              at 14:32│
├──────────────────────────────────────┤
│ NASDAQ           14523.10(+0.87%)    │
│ [=========█══════════════════════]   │
├──────────────────────────────────────┤
│ UNH(PRE)           512.40(-0.34%)   │
│ [═══════════════█═════════════════]  │
└──────────────────────────────────────┘
```

**Symbols** are entered as a comma-separated list, e.g.:

```
^IXIC,^GSPC,GC=F,BZ=F
```

- If more than 4 symbols are given, all are fetched and the **4 with the highest absolute % change** are shown.
- Append `(top)` to a symbol to **pin** it — it is always shown regardless of rank. At most 4 `(top)` symbols are allowed.
- Example: `^IXIC(top),UNH,AAPL,TSLA,GC=F`

**Display names**: well-known tickers are shown with friendly names (`NASDAQ`, `S&P 500`, `GOLD`, `BRENT`, etc.). All other symbols display their raw ticker code (e.g. `AAPL`, `UNH`).

**Extended-hours prices**: when the market is in pre- or post-market session the extended-hours price is used and the label `(PRE)` or `(POST)` is appended to the symbol. The change % shown reflects only that session's move.

**Template data fields** (for API / config use):

| Field | Type | Description |
|---|---|---|
| `symbols` | string or list | Comma-separated ticker codes (with optional `(top)` suffix) |

Legacy fields `sym1`–`sym4` are also accepted for backwards compatibility.

## API

### `GET /api/health`

```json
{
  "status": "ok",
  "version": "0.2.0",
  "devices": 1,
  "queue_depth": 0,
  "last_refresh": "2024-01-15T14:32:00",
  "next_refresh_in": 187
}
```

### `POST /api/push`

Push arbitrary text to the display (queued).

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

### `POST /api/push/template`

Render a named template and push to the display.

```bash
curl -X POST http://localhost:8420/api/push/template \
  -H "Content-Type: application/json" \
  -d '{"template": "stock", "data": {"symbols": "^IXIC,UNH(top),AAPL,TSLA"}}'
```

### `POST /api/push/stocks`

Fetch live stock quotes and push to the display. Defaults to NASDAQ, S&P 500, Gold, Brent.

```bash
curl -X POST http://localhost:8420/api/push/stocks \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["^IXIC", "UNH(top)", "AAPL", "TSLA", "GC=F"]}'
```

### `POST /api/preview/template`

Render a template and return a PNG image without pushing to the display.

```bash
curl -X POST http://localhost:8420/api/preview/template \
  -H "Content-Type: application/json" \
  -d '{"template": "stock", "data": {"symbols": "^IXIC,AAPL"}}' \
  --output preview.png
```

### `POST /api/preview/stocks`

Fetch live quotes and return a rendered PNG without pushing.

```bash
curl -X POST http://localhost:8420/api/preview/stocks \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["^IXIC", "AAPL"]}' \
  --output preview.png
```

### `GET /api/templates`

List available template names.

```json
{"templates": ["stock"]}
```

### `GET /api/config` / `PATCH /api/config`

Read or update persistent configuration.

```bash
# Enable auto-refresh every 5 minutes with the stock template
curl -X PATCH http://localhost:8420/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "template": "stock",
    "template_data": {"symbols": "^IXIC(top),UNH,AAPL,TSLA"},
    "refresh_interval": 300
  }'
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

## Credits / Thanks

Special thanks to the following open-source projects for their excellent work and reference implementations of the protocols used to communicate with these types of e-ink displays:

- [yihong0618/bbtag](https://github.com/yihong0618/bbtag)
- [fuergaosi233/cc-usage-elink](https://github.com/fuergaosi233/cc-usage-elink)
