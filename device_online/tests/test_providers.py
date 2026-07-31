from __future__ import annotations

from device_online.models import DeviceStatus
from device_online.providers import DahuaProvider, IntelbrasProvider, get_provider


def test_provider_factory_defaults_to_dahua() -> None:
    assert isinstance(get_provider(), DahuaProvider)
    assert isinstance(get_provider("intelbras"), IntelbrasProvider)


def test_status_payload_flattens_metadata() -> None:
    status = DeviceStatus(
        ok=True,
        vendor="intelbras",
        serial="TEST123",
        online=True,
        raw_code=1,
        metadata={"direct_query": 1},
    )
    payload = status.to_payload()
    assert payload["online"] is True
    assert payload["direct_query"] == 1
