from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class DeviceResponse:
    ok: bool
    vendor: str
    serial: str
    error: str | None = None
    checked_at: str = field(default_factory=utc_now_iso)
    raw_code: int | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceStatus(DeviceResponse):
    online: bool = False
    device_addr: str | None = None
    egress_ip: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.update(self.metadata)
        return payload


@dataclass
class DeviceInfo(DeviceResponse):
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceSession(DeviceResponse):
    session_id: str | None = None
    authenticated: bool = False
