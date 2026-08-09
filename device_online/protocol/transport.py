from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Callable
from typing import Iterable

EndpointResolver = Callable[[str, int, int], tuple]


def host_is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def parse_ip_pool(value: str, family: int | None = None) -> list[str]:
    ips: list[str] = []
    for item in value.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if ip.is_loopback:
            continue
        if family == socket.AF_INET and ip.version != 4:
            continue
        if family == socket.AF_INET6 and ip.version != 6:
            continue
        ips.append(str(ip))
    return ips


def default_resolver(host: str, port: int, family: int) -> tuple:
    if host_is_ip(host):
        return (host, port)
    infos = socket.getaddrinfo(host, port, family, socket.SOCK_DGRAM)
    if not infos:
        raise RuntimeError(f"no address resolved for {host}:{port}")
    return infos[0][4]


class RoundRobinIpResolver:
    def __init__(self, hostname: str, configured_ips: Iterable[str] = ()) -> None:
        self.hostname = hostname
        self._by_family = {
            socket.AF_INET: [ip for ip in configured_ips if ":" not in ip],
            socket.AF_INET6: [ip for ip in configured_ips if ":" in ip],
        }
        self._lock = threading.Lock()
        self._idx = 0

    def __call__(self, host: str, port: int, family: int) -> tuple:
        if host == self.hostname:
            pool = self._by_family.get(family, [])
            if pool:
                with self._lock:
                    ip = pool[self._idx % len(pool)]
                    self._idx += 1
                return (ip, port)
        return default_resolver(host, port, family)


class UdpTransport:
    def __init__(
        self,
        *,
        timeout: float = 5.0,
        bind_ip: str | None = None,
        bind_fallback: bool = True,
        resolver: EndpointResolver | None = None,
        max_bytes: int = 8192,
    ) -> None:
        self.timeout = timeout
        self.bind_ip = bind_ip
        self.bind_fallback = bind_fallback
        self.resolver = resolver or default_resolver
        self.max_bytes = max_bytes

    def _socket(self) -> socket.socket:
        family = socket.AF_INET6 if self.bind_ip and ":" in self.bind_ip else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        bind_host = self.bind_ip or ("::" if family == socket.AF_INET6 else "0.0.0.0")
        try:
            sock.bind((bind_host, 0))
        except PermissionError:
            sock.close()
            if not self.bind_ip or not self.bind_fallback:
                raise
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            sock.bind(("0.0.0.0", 0))
        return sock

    def open_socket(self) -> socket.socket:
        return self._socket()

    def send_on_socket(
        self,
        sock: socket.socket,
        host: str,
        port: int,
        payload: bytes,
        *,
        receive: bool = True,
    ) -> bytes | None:
        remote = self.resolver(host, port, sock.family)
        sock.sendto(payload, remote)
        if not receive:
            return None
        return self.receive_on_socket(sock, host, port)

    def receive_on_socket(self, sock: socket.socket, host: str, port: int) -> bytes:
        try:
            data, _addr = sock.recvfrom(self.max_bytes)
        except socket.timeout as exc:
            raise TimeoutError(f"timeout waiting response from {host}:{port}") from exc
        return data

    def send(self, host: str, port: int, payload: bytes, *, receive: bool = True) -> bytes | None:
        with self._socket() as sock:
            return self.send_on_socket(sock, host, port, payload, receive=receive)

    def request(self, host: str, port: int, payload: bytes) -> bytes:
        data = self.send(host, port, payload, receive=True)
        if data is None:
            raise RuntimeError("empty UDP response")
        return data
