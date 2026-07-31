from __future__ import annotations

import os

from ..models import DeviceStatus
from ..protocol.intelbras_packets import (
    LOGIN_PACKET,
    T2U_CMD_LOGIN_RESPONSE,
    T2U_MAGIC,
    build_query_request,
    parse_query_response,
    parse_query_servers,
)
from ..protocol.transport import UdpTransport
from .base import DeviceProvider


class IntelbrasProvider(DeviceProvider):
    vendor = "intelbras"

    def __init__(
        self,
        *,
        timeout: float | None = None,
        query_servers: str | list[tuple[str, int]] | None = None,
        transport_factory: type[UdpTransport] = UdpTransport,
    ) -> None:
        self.timeout = timeout if timeout is not None else float(os.getenv("T2U_DIRECT_TIMEOUT_SECS", "5.0"))
        if isinstance(query_servers, str):
            self.query_servers = parse_query_servers(query_servers)
        elif query_servers is None:
            env_query_servers = os.getenv("T2U_QUERY_SERVERS")
            self.query_servers = parse_query_servers(env_query_servers) if env_query_servers else parse_query_servers()
        else:
            self.query_servers = list(query_servers)
        self.transport_factory = transport_factory

    def online(self, serial: str) -> DeviceStatus:
        clean = str(serial or "").strip()
        if not clean:
            return DeviceStatus(ok=False, vendor=self.vendor, serial="", online=False, error="missing serial")
        try:
            result = self._direct_query(clean)
            return DeviceStatus(
                ok=result["ok"],
                vendor=self.vendor,
                serial=clean,
                online=result["online"],
                raw_code=result["query_ret"],
                device_addr=result["device_addr"],
                error=result["error"],
                metadata={
                    "direct_query": result["query_ret"],
                    "server": result["server"],
                    "port": result["port"],
                    "response_hex_prefix": result["response_hex_prefix"],
                },
            )
        except Exception as exc:
            return DeviceStatus(ok=False, vendor=self.vendor, serial=clean, online=False, error=str(exc))

    def _direct_query(self, serial: str) -> dict:
        errors: list[str] = []
        if not LOGIN_PACKET:
            raise ValueError("T2U_LOGIN_PACKET_HEX is required for Intelbras direct queries")
        request = build_query_request(serial)
        for host, port in self.query_servers:
            transport = self.transport_factory(timeout=self.timeout, max_bytes=4096)
            try:
                login_response = transport.request(host, port, LOGIN_PACKET)
                if len(login_response) < 4:
                    raise ValueError(f"short login response: {len(login_response)} bytes")
                login_magic = int.from_bytes(login_response[:2], "little")
                login_command = int.from_bytes(login_response[2:4], "little")
                if login_magic != T2U_MAGIC or login_command != T2U_CMD_LOGIN_RESPONSE:
                    raise ValueError(
                        f"unexpected login response magic=0x{login_magic:04x} command=0x{login_command:04x}"
                    )
            except Exception as exc:
                errors.append(f"{host}:{port} login failed: {exc}")
                continue

            transport = self.transport_factory(timeout=self.timeout, max_bytes=4096)
            try:
                response = transport.request(host, port, request)
                parsed = parse_query_response(response, serial)
                return {
                    "ok": parsed.ok,
                    "online": parsed.online,
                    "query_ret": parsed.query_ret,
                    "device_addr": parsed.device_addr,
                    "server": host,
                    "port": port,
                    "response_hex_prefix": parsed.response_hex_prefix,
                    "error": None,
                }
            except Exception as exc:
                errors.append(f"{host}:{port} query failed: {exc}")

        return {
            "ok": False,
            "online": False,
            "query_ret": None,
            "device_addr": None,
            "server": None,
            "port": None,
            "response_hex_prefix": "",
            "error": "; ".join(errors) or "all query servers failed",
        }
