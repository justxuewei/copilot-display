from __future__ import annotations

from pydantic import BaseModel


class PushTextRequest(BaseModel):
    body: str
    title: str | None = None
    title_color: str = "red"
    body_color: str = "black"
    device: str | None = None


class DeviceInfo(BaseModel):
    name: str
    address: str
    rssi: int | None = None
