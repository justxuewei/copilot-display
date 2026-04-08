from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PushTextRequest(BaseModel):
    body: str
    title: str | None = None
    title_color: str = "red"
    body_color: str = "black"
    device: str | None = None


class PushTemplateRequest(BaseModel):
    template: str
    data: dict[str, Any]
    device: str | None = None


class PushStocksRequest(BaseModel):
    symbols: list[str] | None = None  # up to 4 ticker codes
    device: str | None = None


class DeviceInfo(BaseModel):
    name: str
    address: str
    rssi: int | None = None
