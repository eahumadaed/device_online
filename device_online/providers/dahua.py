from __future__ import annotations

import os

from ..models import DeviceStatus
from ..protocol.dahua_packets import DahuaDhResponse, DahuaPacketCodec, parse_response, split_host_port, tag_value
from ..protocol.transport import RoundRobinIpResolver, UdpTransport, parse_ip_pool
from .base import DeviceProvider


DEFAULT_USERNAME = "cba1b29e32cb17aa46b8ff9e73c7f40b"
DEFAULT_USERKEY = "996103384cdf19179e19243e959bbf8b"
DEFAULT_MAIN_SERVER_IPS = ""


class DahuaProvider(DeviceProvider):
    vendor = "dahua"

    def __init__(
        self,
        *,
        main_server: str | None = None,
        main_port: int | None = None,
        username: str | None = None,
        userkey: str | None = None,
        timeout: float | None = None,
        egress_ip: str | None = None,
        main_server_ips: str | None = None,
        bind_fallback: bool | None = None,
        transport: UdpTransport | None = None,
    ) -> None:
        self.main_server = main_server or os.getenv("DH_MAIN_SERVER", "www.easy4ipcloud.com")
        self.main_port = main_port or int(os.getenv("DH_MAIN_PORT", "8800"))
        self.timeout = timeout if timeout is not None else float(os.getenv("DH_UDP_TIMEOUT_SECS", "5.0"))
        self.egress_ip = egress_ip
        self.codec = DahuaPacketCodec(
            username=username or os.getenv("DH_USERNAME", DEFAULT_USERNAME),
            userkey=userkey or os.getenv("DH_USERKEY", DEFAULT_USERKEY),
        )
        if bind_fallback is None:
            bind_fallback = os.getenv("BIND_EGRESS_FALLBACK", "1").lower() not in {"0", "false", "no"}
        ip_pool = parse_ip_pool(main_server_ips or os.getenv("DH_MAIN_SERVER_IPS", DEFAULT_MAIN_SERVER_IPS))
        self.transport = transport or UdpTransport(
            timeout=self.timeout,
            bind_ip=egress_ip,
            bind_fallback=bind_fallback,
            resolver=RoundRobinIpResolver(self.main_server, ip_pool),
        )

    def online(self, serial: str) -> DeviceStatus:
        clean = str(serial or "").strip()
        if not clean:
            return DeviceStatus(ok=False, vendor=self.vendor, serial="", online=False, error="missing serial")
        try:
            online = self._check_online(clean)
            return DeviceStatus(
                ok=True,
                vendor=self.vendor,
                serial=clean,
                online=online,
                raw_code=1 if online else 0,
                egress_ip=self.egress_ip,
            )
        except Exception as exc:
            return DeviceStatus(
                ok=False,
                vendor=self.vendor,
                serial=clean,
                online=False,
                error=str(exc),
                egress_ip=self.egress_ip,
            )

    def _request(
        self,
        host: str,
        port: int,
        path: str,
        *,
        body: str = "",
        with_auth: bool = True,
    ) -> DahuaDhResponse:
        raw = self.transport.request(host, port, self.codec.build_request(path, body, with_auth=with_auth))
        return parse_response(raw)

    def _check_online(self, serial: str) -> bool:
        p2p_info = self._request(self.main_server, self.main_port, f"/online/p2psrv/{serial}")
        if p2p_info.code >= 400:
            return False

        us = tag_value(p2p_info.body, "US")
        if not us:
            return False

        p2p_host, p2p_port = split_host_port(us)

        def query_probe_info(with_auth: bool) -> tuple[DahuaDhResponse, DahuaDhResponse]:
            probe_response = self._request(p2p_host, p2p_port, f"/probe/device/{serial}", with_auth=with_auth)
            info_response = self._request(p2p_host, p2p_port, f"/info/device/{serial}", with_auth=with_auth)
            return probe_response, info_response

        probe, info = query_probe_info(with_auth=True)
        key_error_auth = probe.code == 401 and "KeyError" in probe.body
        key_error_auth = key_error_auth or (info.code == 401 and "KeyError" in info.body)
        if key_error_auth:
            probe, info = query_probe_info(with_auth=False)

        if probe.code >= 400 or info.code >= 400:
            return False
        return bool(info.body.strip())
