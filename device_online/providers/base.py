from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import DeviceInfo, DeviceSession, DeviceStatus


class DeviceProvider(ABC):
    vendor = "unknown"

    @abstractmethod
    def online(self, serial: str) -> DeviceStatus:
        raise NotImplementedError

    def info(self, serial: str) -> DeviceInfo:
        return DeviceInfo(
            ok=False,
            vendor=self.vendor,
            serial=str(serial or "").strip(),
            error=f"{self.vendor} info is not implemented",
        )

    def login(self, *args: Any, **kwargs: Any) -> DeviceSession:
        return DeviceSession(
            ok=False,
            vendor=self.vendor,
            serial=str(kwargs.get("serial") or ""),
            error=f"{self.vendor} login is not implemented",
        )

    def logout(self, *args: Any, **kwargs: Any) -> DeviceResponseLike:
        return DeviceSession(
            ok=True,
            vendor=self.vendor,
            serial=str(kwargs.get("serial") or ""),
            authenticated=False,
        )


DeviceResponseLike = DeviceInfo | DeviceSession | DeviceStatus


def get_provider(vendor: str = "dahua", **kwargs: Any) -> DeviceProvider:
    normalized = (vendor or "dahua").strip().lower().replace("-", "_")
    if normalized in {"dahua", "dh", "easy4ip"}:
        from .dahua import DahuaProvider

        return DahuaProvider(**kwargs)
    if normalized in {"intelbras", "intelbras_direct", "ibcloud_direct", "t2u"}:
        from .intelbras import IntelbrasProvider

        return IntelbrasProvider(**kwargs)
    raise ValueError(f"unknown provider vendor: {vendor}")
