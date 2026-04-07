"""FastAPI server for pushing text to a BluTag 4.2-inch e-ink display."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic_settings import BaseSettings, SettingsConfigDict

from copilot_display import __version__
from copilot_display.ble import get_cached_devices, push_image, scan_devices
from copilot_display.models import PushTextRequest
from copilot_display.render import render_text

logger = logging.getLogger("copilot_display")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COPILOT_DISPLAY_")

    api_token: str = ""
    host: str = "0.0.0.0"
    port: int = 8420
    scan_interval: int = 60


settings = Settings()

# Task queue and state store
_queue: asyncio.Queue = asyncio.Queue()
_tasks: dict[str, dict[str, Any]] = {}


async def _background_scan(interval: int) -> None:
    while True:
        try:
            await scan_devices(timeout=8.0)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Starting copilot-display v%s", __version__)
    scan_task = asyncio.create_task(_background_scan(settings.scan_interval))
    worker_task = asyncio.create_task(_queue_worker())
    yield
    scan_task.cancel()
    worker_task.cancel()
    for t in (scan_task, worker_task):
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
    return {
        "status": "ok",
        "version": __version__,
        "devices": len(get_cached_devices()),
        "queue_depth": _queue.qsize(),
    }


@app.get("/api/devices")
async def list_devices():
    return get_cached_devices()


@app.post("/api/devices/scan")
async def trigger_scan():
    devices = await scan_devices(timeout=10.0)
    return {"found": len(devices), "devices": devices}


@app.post("/api/test/black", status_code=202)
async def test_black(device: str | None = None):
    """Send all-black image for display test."""
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (400, 300), (0, 0, 0))
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "queued", "queue_position": _queue.qsize() + 1}
    await _queue.put((task_id, img, device))
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/clear", status_code=202)
async def clear_endpoint(device: str | None = None):
    """Send all-white image to clear the display."""
    from PIL import Image as PILImage
    white = PILImage.new("RGB", (400, 300), (255, 255, 255))
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "queued", "queue_position": _queue.qsize() + 1}
    await _queue.put((task_id, white, device))
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
    await _queue.put((task_id, img, req.device))
    logger.info("Enqueued task %s (queue depth: %d)", task_id, _queue.qsize())

    return {"task_id": task_id, "status": "queued"}


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
