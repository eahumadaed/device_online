from __future__ import annotations

import os
from typing import Any

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
            metadata: dict[str, Any] = {}
            device_addr = None
            if online and os.getenv("DH_PUBADDR_LOOKUP", "1").lower() not in {"0", "false", "no"}:
                nat = self.lookup_nat_addr(clean)
                pubaddr = nat.get("pubaddr") or nat.get("pub_addr")
                local_addr = nat.get("local_addr")
                device_addr = pubaddr or local_addr
                if pubaddr:
                    metadata.update(
                        {
                            "PubAddr": pubaddr,
                            "pubaddr": pubaddr,
                            "pub_addr": pubaddr,
                            "pub_addr_raw": pubaddr,
                        }
                    )
                if local_addr:
                    metadata.update({"LocalAddr": local_addr, "local_addr_raw": local_addr})
                if nat.get("host_ip"):
                    metadata["host_ip"] = nat["host_ip"]
                if nat.get("error"):
                    metadata["pubaddr_error"] = nat["error"]
            return DeviceStatus(
                ok=True,
                vendor=self.vendor,
                serial=clean,
                online=online,
                raw_code=1 if online else 0,
                device_addr=device_addr,
                egress_ip=self.egress_ip,
                metadata=metadata,
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
        sock: Any | None = None,
        read: bool = True,
    ) -> DahuaDhResponse | None:
        payload = self.codec.build_request(path, body, with_auth=with_auth)
        if sock is None:
            if not read:
                self.transport.send(host, port, payload, receive=False)
                return None
            raw = self.transport.request(host, port, payload)
            return parse_response(raw)
        raw = self.transport.send_on_socket(sock, host, port, payload, receive=read)
        return parse_response(raw) if raw is not None else None

    def _check_online(self, serial: str) -> bool:
        p2p_info = self._request(self.main_server, self.main_port, f"/online/p2psrv/{serial}")
        if p2p_info is None or p2p_info.code >= 400:
            return False

        us = tag_value(p2p_info.body, "US")
        if not us:
            return False

        p2p_host, p2p_port = split_host_port(us)

        def query_probe_info(with_auth: bool) -> tuple[DahuaDhResponse, DahuaDhResponse]:
            probe_response = self._request(p2p_host, p2p_port, f"/probe/device/{serial}", with_auth=with_auth)
            info_response = self._request(p2p_host, p2p_port, f"/info/device/{serial}", with_auth=with_auth)
            if probe_response is None or info_response is None:
                raise RuntimeError("empty probe/info response")
            return probe_response, info_response

        probe, info = query_probe_info(with_auth=True)
        key_error_auth = probe.code == 401 and "KeyError" in probe.body
        key_error_auth = key_error_auth or (info.code == 401 and "KeyError" in info.body)
        if key_error_auth:
            probe, info = query_probe_info(with_auth=False)

        if probe.code >= 400 or info.code >= 400:
            return False
        return bool(info.body.strip())

    def lookup_nat_addr(self, serial: str) -> dict[str, Any]:
        sockets: list[Any] = []

        def open_sock() -> Any:
            sock = self.transport.open_socket()
            sockets.append(sock)
            return sock

        try:
            main_sock = open_sock()
            p2p_info = self._request(
                self.main_server,
                self.main_port,
                f"/online/p2psrv/{serial}",
                sock=main_sock,
            )
            if p2p_info is None or p2p_info.code >= 400:
                return {"ok": False, "error": "p2psrv lookup failed"}

            upstream = tag_value(p2p_info.body, "US")
            if not upstream:
                return {"ok": False, "error": "p2psrv lookup missing US"}

            p2p_host, p2p_port = split_host_port(upstream)
            p2p_sock = open_sock()
            probe = self._request(p2p_host, p2p_port, f"/probe/device/{serial}", sock=p2p_sock)
            info = self._request(p2p_host, p2p_port, f"/info/device/{serial}", sock=p2p_sock)
            if probe is None or info is None or probe.code >= 400 or info.code >= 400:
                return {"ok": False, "error": "device probe/info failed"}

            relay_lookup = self._request(self.main_server, self.main_port, "/online/relay", sock=main_sock)
            relay_addr = tag_value(relay_lookup.body, "Address") if relay_lookup else None
            if relay_lookup is None or relay_lookup.code >= 400 or not relay_addr:
                return {"ok": False, "error": "relay lookup failed"}
            relay_host, relay_port = split_host_port(relay_addr)

            device_sock = open_sock()
            local_port = device_sock.getsockname()[1]
            local_advertised = f"127.0.0.1:{local_port}"
            identify = " ".join(f"{byte:x}" for byte in os.urandom(8))
            p2p_body = (
                "<body>"
                f"<Identify>{identify}</Identify>"
                "<IpEncrpt>true</IpEncrpt>"
                f"<LocalAddr>{local_advertised}</LocalAddr>"
                "<version>5.0.0</version>"
                "</body>"
            )
            self._request(
                self.main_server,
                self.main_port,
                f"/device/{serial}/p2p-channel",
                body=p2p_body,
                sock=device_sock,
                read=False,
            )

            relay_sock = open_sock()
            agent_response = self._request(relay_host, relay_port, "/relay/agent", sock=relay_sock)
            token = tag_value(agent_response.body, "Token") if agent_response else None
            agent_addr = tag_value(agent_response.body, "Agent") if agent_response else None
            if agent_response is None or agent_response.code >= 400 or not token or not agent_addr:
                return {"ok": False, "error": "relay agent failed"}
            agent_host, agent_port = split_host_port(agent_addr)
            self._request(
                agent_host,
                agent_port,
                f"/relay/start/{token}",
                body="<body><Client>:0</Client></body>",
                sock=relay_sock,
            )

            local_addr = None
            pub_addr = None
            for _ in range(3):
                try:
                    raw = self.transport.receive_on_socket(device_sock, self.main_server, self.main_port)
                except TimeoutError:
                    break
                response = parse_response(raw)
                local_addr = tag_value(response.body, "LocalAddr") or local_addr
                pub_addr = tag_value(response.body, "PubAddr") or pub_addr
                if local_addr or pub_addr:
                    break

            host_ip = pub_addr.rsplit(":", 1)[0] if pub_addr and ":" in pub_addr else None
            return {
                "ok": bool(local_addr or pub_addr),
                "local_addr": local_addr,
                "pub_addr": pub_addr,
                "pubaddr": pub_addr,
                "host_ip": host_ip,
                "error": None if local_addr or pub_addr else "NAT response did not include address",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            for sock in sockets:
                try:
                    sock.close()
                except OSError:
                    pass
