"""FastAPI server for pushing text to a BluTag 4.2-inch e-ink display."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

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


async def _background_scan(interval: int) -> None:
    while True:
        try:
            await scan_devices(timeout=8.0)
        except Exception:
            logger.exception("Background scan failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Starting copilot-display v%s", __version__)
    task = asyncio.create_task(_background_scan(settings.scan_interval))
    yield
    task.cancel()
    try:
        await task
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
    }


@app.get("/api/devices")
async def list_devices():
    return get_cached_devices()


@app.post("/api/devices/scan")
async def trigger_scan():
    devices = await scan_devices(timeout=10.0)
    return {"found": len(devices), "devices": devices}


@app.post("/api/push")
async def push_text(req: PushTextRequest):
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="body must not be empty")

    img = render_text(
        body=req.body,
        title=req.title,
        title_color=req.title_color,
        body_color=req.body_color,
    )

    try:
        result = await push_image(img, device_address=req.device)
    except RuntimeError as e:
        msg = str(e)
        if "Another push" in msg:
            raise HTTPException(status_code=409, detail=msg)
        if "No BluTag" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=502, detail=msg)

    return result


def main():
    uvicorn.run(
        "copilot_display.server:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
