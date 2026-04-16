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
from fastapi.responses import FileResponse, HTMLResponse, Response
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
_cleanup_task:    asyncio.Task | None = None
_next_task_cleanup_at: datetime | None = None

# Statuses that indicate a task has reached a terminal state.
# Includes "ok" (legacy: was returned by push_image before the ble_status rename)
# and "error" as defensive catches for any unexpected values.
_TERMINAL_STATUSES = {"done", "failed", "ok", "error"}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _new_task(status: str = "queued", *, queue_position: int | None = None, **extra: Any) -> dict[str, Any]:
    now = _now_iso()
    return {
        "status": status,
        "queue_position": queue_position,
        "created_at": now,
        "updated_at": now,
        **extra,
    }


def _update_task(task_id: str, *, timestamp: str | None = None, **updates: Any) -> dict[str, Any]:
    task = _tasks[task_id]
    stamp = timestamp or _now_iso()
    task.update(updates)
    task["updated_at"] = stamp
    return task


async def _enqueue_task(img: Any, device: str | None) -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = _new_task(queue_position=_queue.qsize() + 1)
    await _queue.put((task_id, img, device))
    return task_id


def _queued_positions() -> dict[str, int]:
    queued_pos: dict[str, int] = {}
    pos = 1
    for tid, info in _tasks.items():
        if info.get("status") == "queued":
            queued_pos[tid] = pos
            pos += 1
    return queued_pos


def _serialize_task(task_id: str, info: dict[str, Any], queued_pos: dict[str, int] | None = None) -> dict[str, Any]:
    queued_pos = queued_pos or {}
    entry = {"task_id": task_id, **info}
    status = info.get("status")
    if status == "queued":
        entry["queue_position"] = queued_pos.get(task_id, info.get("queue_position"))
    elif status == "in_progress":
        entry["queue_position"] = 0
    else:
        entry["queue_position"] = None
    return entry


def _parse_hhmm(value: str, default: dt_time = dt_time(0, 0)) -> dt_time:
    try:
        hour, minute = value.split(":", 1)
        return dt_time(int(hour), int(minute))
    except (AttributeError, TypeError, ValueError):
        return default


def _next_daily_time(clear_time: dt_time, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    next_at = datetime.combine(now.date(), clear_time)
    if next_at <= now:
        next_at += timedelta(days=1)
    return next_at


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
        _update_task(task_id, **{
            "status": "in_progress",
            "queue_position": 0,
            "black_sent": 0, "black_total": 0,
            "red_sent":   0, "red_total":   0,
        })
        logger.info("Processing task %s", task_id)

        def on_progress(channel: str, sent: int, total: int) -> None:
            if channel == "black":
                _update_task(task_id, black_sent=sent, black_total=total)
            else:
                _update_task(task_id, red_sent=sent, red_total=total)

        try:
            result = await push_image(img, device_address=device, on_progress=on_progress)
            completed_at = _now_iso()
            _update_task(task_id, timestamp=completed_at, status="done", completed_at=completed_at, **result)
        except Exception as e:
            logger.exception("Task %s failed", task_id)
            completed_at = _now_iso()
            _update_task(task_id, timestamp=completed_at, status="failed", completed_at=completed_at, error=str(e))
        finally:
            _queue.task_done()


def _delete_finished_tasks() -> int:
    stale = [tid for tid, info in _tasks.items() if info.get("status") in _TERMINAL_STATUSES]
    for tid in stale:
        del _tasks[tid]
    return len(stale)


async def _task_cleanup_worker() -> None:
    """Remove finished tasks once per day at the configured local time."""
    global _next_task_cleanup_at
    while True:
        config = store.load_config()
        clear_time = _parse_hhmm(config.get("task_clear_time", "00:00"))
        _next_task_cleanup_at = _next_daily_time(clear_time)
        logger.info("Next finished-task cleanup scheduled at %s", _next_task_cleanup_at.isoformat())
        await asyncio.sleep(max(0, (_next_task_cleanup_at - datetime.now()).total_seconds()))
        if not store.load_config().get("auto_clear_finished_tasks", False):
            logger.info("Finished-task cleanup skipped: disabled")
            continue
        deleted = _delete_finished_tasks()
        if deleted:
            logger.info("Pruned %d finished task(s) from queue history", deleted)


async def _restart_task_cleanup(config: dict | None = None) -> None:
    global _cleanup_task, _next_task_cleanup_at
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None

    config = config or store.load_config()
    if config.get("auto_clear_finished_tasks", False):
        _cleanup_task = asyncio.create_task(_task_cleanup_worker())
        logger.info("Finished-task cleanup enabled (time=%s)", config.get("task_clear_time", "00:00"))
    else:
        _next_task_cleanup_at = None
        logger.info("Finished-task cleanup disabled")


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
    task_id = await _enqueue_task(img, device)
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
    worker_task = asyncio.create_task(_queue_worker())
    await _restart_task_cleanup(config)
    scan_interval = config.get("scan_interval", settings.scan_interval)
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
    for t in filter(None, (scan_task, _refresh_task, _cleanup_task)):
        t.cancel()
    worker_task.cancel()
    for t in filter(None, (scan_task, _refresh_task, _cleanup_task, worker_task)):
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(title="copilot-display", version=__version__, lifespan=lifespan)
FAVICON_PATH = Path(__file__).with_name("assets") / "favicon.ico"


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
    next_task_cleanup_in: int | None = None
    if _next_task_cleanup_at is not None:
        next_task_cleanup_in = max(0, int((_next_task_cleanup_at - datetime.now()).total_seconds()))
    config = store.load_config()
    return {
        "status": "ok",
        "version": __version__,
        "devices": len(get_cached_devices()),
        "queue_depth": _queue.qsize(),
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None,
        "next_refresh_in": next_refresh_in,
        "next_task_cleanup_in": next_task_cleanup_in,
        "is_work_time": _is_work_time(config),
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
    task_id = await _enqueue_task(white, device or settings.device_address or None)
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

    task_id = await _enqueue_task(img, req.device or settings.device_address or None)
    logger.info("Enqueued task %s (queue depth: %d)", task_id, _queue.qsize())

    return {"task_id": task_id, "status": "queued"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui_page():
    """Interactive template preview and control UI."""
    return UI_HTML


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve the web UI favicon."""
    return FileResponse(FAVICON_PATH, media_type="image/x-icon")


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
    if "auto_clear_finished_tasks" in updates or "task_clear_time" in updates:
        await _restart_task_cleanup(config)
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

    task_id = await _enqueue_task(img, req.device or settings.device_address or None)
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

    task_id = await _enqueue_task(img, device)
    logger.info(
        "Enqueued stocks task %s (symbols=%s, queue depth: %d)",
        task_id,
        symbols,
        _queue.qsize(),
    )
    return {"task_id": task_id, "status": "queued", "symbols": symbols, "data": data}


@app.get("/api/tasks")
async def list_tasks():
    # Recompute queue positions live: "queued" tasks get sequential positions
    # in insertion order; "in_progress" is always 0; finished tasks get None.
    queued_pos = _queued_positions()

    result = []
    for tid, info in _tasks.items():
        result.append(_serialize_task(tid, info, queued_pos))
    return result



@app.delete("/api/tasks/done", status_code=204)
async def delete_done_tasks():
    """Remove all finished (done/failed) tasks from the queue history."""
    logger.info("delete_done_tasks: total tasks=%d, statuses=%s",
                len(_tasks), {tid: info.get("status") for tid, info in _tasks.items()})
    deleted = _delete_finished_tasks()
    logger.info("delete_done_tasks: removed %d finished task(s)", deleted)
    logger.info("delete_done_tasks: done, remaining tasks=%d", len(_tasks))


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _serialize_task(task_id, task, _queued_positions())


def main():
    uvicorn.run(
        "copilot_display.server:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
