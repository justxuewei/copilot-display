"""FastAPI server for pushing text to a BluTag 4.2-inch e-ink display."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, time as dt_time, timedelta
from typing import Any

import io

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic_settings import BaseSettings, SettingsConfigDict

from copilot_display import __version__, templates
from copilot_display.ble import clear_display, get_cached_devices, push_image, scan_devices, set_cached_devices
from copilot_display.models import PushStocksRequest, PushTemplateRequest, PushTextRequest
from copilot_display.templates.stock import DEFAULT_SYMBOLS, fetch_quotes
from copilot_display.ui import UI_HTML
from copilot_display.render import render_text
from copilot_display.store import DataStore

logger = logging.getLogger("copilot_display")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COPILOT_DISPLAY_")

    api_token: str = ""
    host: str = "0.0.0.0"
    port: int = 8420
    scan_interval: int = 60
    device_address: str = "FF:FF:42:00:11:1C"
    data_dir: Path = Path("/etc/codisplay")


settings = Settings()
store = DataStore(settings.data_dir)

# Task queue and state store
_queue: asyncio.Queue = asyncio.Queue()
_tasks: dict[str, dict[str, Any]] = {}
_last_refresh:    datetime | None = None
_last_scan:       datetime | None = None
_next_refresh_at: datetime | None = None
_refresh_task:    asyncio.Task | None = None


def _load_timestamps() -> None:
    global _last_refresh, _last_scan
    state = store.load_state()
    for key, var in (("last_refresh", "_last_refresh"), ("last_scan", "_last_scan")):
        val = state.get(key)
        if val:
            try:
                globals()[var] = datetime.fromisoformat(val)
            except ValueError:
                pass


def _save_timestamps() -> None:
    store.save_state({
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None,
        "last_scan":    _last_scan.isoformat()    if _last_scan    else None,
    })


async def _background_scan(interval: int) -> None:
    global _last_scan
    while True:
        try:
            await scan_devices(timeout=8.0)
            store.save_devices(get_cached_devices())
            _last_scan = datetime.now()
            _save_timestamps()
        except Exception:
            logger.exception("Background scan failed")
        await asyncio.sleep(interval)


async def _queue_worker() -> None:
    while True:
        task_id, img, device = await _queue.get()
        _tasks[task_id]["status"] = "in_progress"
        logger.info("Processing task %s", task_id)
        try:
            result = await push_image(img, device_address=device)
            _tasks[task_id].update({"status": "done", **result})
        except Exception as e:
            logger.exception("Task %s failed", task_id)
            _tasks[task_id].update({"status": "failed", "error": str(e)})
        finally:
            _queue.task_done()


def _is_work_time(config: dict) -> bool:
    now = datetime.now()
    work_days = config.get("work_days", [])
    if work_days and now.weekday() not in work_days:
        return False
    work_start = config.get("work_start", "")
    work_end   = config.get("work_end",   "")
    if work_start and work_end:
        def _t(s): h, m = s.split(":"); return dt_time(int(h), int(m))
        if not (_t(work_start) <= now.time() <= _t(work_end)):
            return False
    return True


async def _do_refresh() -> None:
    global _last_refresh
    config = store.load_config()
    if not _is_work_time(config):
        logger.info("Refresh skipped: outside work hours/days")
        return

    template_name = config.get("template", "")
    if not template_name:
        logger.info("Refresh skipped: no template configured")
        return

    tmpl = templates.get(template_name)
    if tmpl is None:
        logger.warning("Refresh skipped: unknown template '%s'", template_name)
        return

    template_data = config.get("template_data", {})
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, tmpl.fetch, template_data)
    img = tmpl.render(data)

    device = settings.device_address or None
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "queued", "queue_position": _queue.qsize() + 1}
    await _queue.put((task_id, img, device))
    _last_refresh = datetime.now()
    _save_timestamps()
    logger.info("Enqueued refresh task %s (template=%s)", task_id, template_name)


async def _background_refresh(interval: int) -> None:
    global _next_refresh_at
    _next_refresh_at = datetime.now() + timedelta(seconds=interval)
    while True:
        await asyncio.sleep(interval)
        _next_refresh_at = datetime.now() + timedelta(seconds=interval)
        try:
            await _do_refresh()
        except Exception:
            logger.exception("Background refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Starting copilot-display v%s", __version__)
    set_cached_devices(store.load_devices())
    _load_timestamps()
    config = store.load_config()
    logger.info("Config: %s", config)
    scan_interval = config.get("scan_interval", settings.scan_interval)
    worker_task = asyncio.create_task(_queue_worker())
    scan_task = None
    if scan_interval > 0:
        scan_task = asyncio.create_task(_background_scan(scan_interval))
    else:
        logger.info("Background BLE scan disabled (scan_interval=0)")
    global _refresh_task
    refresh_interval = config.get("refresh_interval", 0)
    if refresh_interval > 0:
        _refresh_task = asyncio.create_task(_background_refresh(refresh_interval))
        logger.info("Background refresh enabled (interval=%ds)", refresh_interval)
    else:
        logger.info("Background refresh disabled (refresh_interval=0)")
    yield
    for t in filter(None, (scan_task, _refresh_task)):
        t.cancel()
    worker_task.cancel()
    for t in filter(None, (scan_task, _refresh_task, worker_task)):
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(title="copilot-display", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if settings.api_token and request.url.path.startswith("/api"):
        token = request.headers.get("X-API-Token", "")
        if token != settings.api_token:
            raise HTTPException(status_code=401, detail="Invalid or missing API token")
    return await call_next(request)


@app.get("/api/health")
async def health():
    next_refresh_in: int | None = None
    if _next_refresh_at is not None:
        next_refresh_in = max(0, int((_next_refresh_at - datetime.now()).total_seconds()))
    return {
        "status": "ok",
        "version": __version__,
        "devices": len(get_cached_devices()),
        "queue_depth": _queue.qsize(),
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None,
        "next_refresh_in": next_refresh_in,
    }


@app.get("/api/devices")
async def list_devices():
    return get_cached_devices()


@app.post("/api/devices/scan")
async def trigger_scan():
    devices = await scan_devices(timeout=10.0)
    store.save_devices(devices)
    return {"found": len(devices), "devices": devices}


@app.post("/api/clear", status_code=202)
async def clear_endpoint(device: str | None = None):
    """Send all-white image to clear the display."""
    from PIL import Image as PILImage
    from copilot_display.ble import SCREEN_H, SCREEN_W
    white = PILImage.new("RGB", (SCREEN_W, SCREEN_H), (255, 255, 255))
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "queued", "queue_position": _queue.qsize() + 1}
    await _queue.put((task_id, white, device or settings.device_address or None))
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/push", status_code=202)
async def push_text(req: PushTextRequest):
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="body must not be empty")

    img = render_text(
        body=req.body,
        title=req.title,
        title_color=req.title_color,
        body_color=req.body_color,
    )

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "queued", "queue_position": _queue.qsize() + 1}
    await _queue.put((task_id, img, req.device or settings.device_address or None))
    logger.info("Enqueued task %s (queue depth: %d)", task_id, _queue.qsize())

    return {"task_id": task_id, "status": "queued"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui_page():
    """Interactive template preview and control UI."""
    return UI_HTML


@app.post("/api/preview/template")
async def preview_template(req: PushTemplateRequest):
    """Render a template and return the result as a PNG image (no display push)."""
    tmpl = templates.get(req.template)
    if tmpl is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template '{req.template}'. Available: {templates.list_names()}",
        )

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, tmpl.fetch, req.data)
        img = tmpl.render(data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Template data error: {exc}") from exc

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/api/preview/stocks")
async def preview_stocks(req: PushStocksRequest | None = None):
    """Fetch live quotes and return rendered stock image as PNG (no push)."""
    symbols = (req.symbols if req else None) or DEFAULT_SYMBOLS

    try:
        data = fetch_quotes(symbols)
    except Exception as exc:
        logger.exception("Failed to fetch stock quotes for %s", symbols)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tmpl = templates.get("stock")
    img = tmpl.render(data)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/config")
async def get_config():
    """Return the current persistent configuration."""
    return store.load_config()


@app.patch("/api/config")
async def patch_config(updates: dict[str, Any]):
    """Update one or more config keys and persist to disk."""
    global _refresh_task, _next_refresh_at
    config = store.load_config()
    config.update(updates)
    store.save_config(config)
    if "refresh_interval" in updates:
        if _refresh_task is not None:
            _refresh_task.cancel()
            try:
                await _refresh_task
            except asyncio.CancelledError:
                pass
        new_interval = updates["refresh_interval"]
        if new_interval > 0:
            _next_refresh_at = datetime.now() + timedelta(seconds=new_interval)
            _refresh_task = asyncio.create_task(_background_refresh(new_interval))
            logger.info("Background refresh restarted (interval=%ds)", new_interval)
        else:
            _next_refresh_at = None
            _refresh_task = None
            logger.info("Background refresh disabled")
    return config


@app.get("/api/templates")
async def list_templates():
    """List all available template names."""
    return {"templates": templates.list_names()}


@app.post("/api/push/template", status_code=202)
async def push_template(req: PushTemplateRequest):
    """Render a named template with the supplied data and push to the display."""
    tmpl = templates.get(req.template)
    if tmpl is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template '{req.template}'. Available: {templates.list_names()}",
        )

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, tmpl.fetch, req.data)
        img = tmpl.render(data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Template data error: {exc}") from exc

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "queued", "queue_position": _queue.qsize() + 1}
    await _queue.put((task_id, img, req.device or settings.device_address or None))
    logger.info(
        "Enqueued template task %s (template=%s, queue depth: %d)",
        task_id,
        req.template,
        _queue.qsize(),
    )
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/push/stocks", status_code=202)
async def push_stocks(req: PushStocksRequest | None = None):
    """Fetch live quotes from Yahoo Finance and push to the display.

    Accepts up to 4 ticker symbols. Defaults to NASDAQ, S&P 500, Gold, Brent.
    """
    symbols = (req.symbols if req else None) or DEFAULT_SYMBOLS
    device = (req.device if req else None) or settings.device_address or None

    try:
        data = fetch_quotes(symbols)
    except Exception as exc:
        logger.exception("Failed to fetch stock quotes for %s", symbols)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tmpl = templates.get("stock")
    img = tmpl.render(data)

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "queued", "queue_position": _queue.qsize() + 1}
    await _queue.put((task_id, img, device))
    logger.info(
        "Enqueued stocks task %s (symbols=%s, queue depth: %d)",
        task_id,
        symbols,
        _queue.qsize(),
    )
    return {"task_id": task_id, "status": "queued", "symbols": symbols, "data": data}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, **task}


def main():
    uvicorn.run(
        "copilot_display.server:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
