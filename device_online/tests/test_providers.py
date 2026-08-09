from __future__ import annotations

from device_online.models import DeviceStatus
from device_online.providers import DahuaProvider, IntelbrasProvider, get_provider


def dh_response(body: str, code: int = 200) -> bytes:
    return f"DHHTTP/1.1 {code} OK\r\nCSeq: 1\r\n\r\n{body}".encode("utf-8")


class FakeSocket:
    def __init__(self, port: int) -> None:
        self.family = 2
        self.port = port
        self.closed = False

    def getsockname(self) -> tuple[str, int]:
        return ("127.0.0.1", self.port)

    def close(self) -> None:
        self.closed = True


class FakeDahuaTransport:
    timeout = 1.0

    def __init__(self) -> None:
        self.sockets: list[FakeSocket] = []
        self.requests: list[tuple[str, int, str, str]] = []
        self.async_reads = [
            dh_response("<body><LocalAddr>192.168.1.10:37777</LocalAddr><PubAddr>203.0.113.10:29854</PubAddr></body>")
        ]

    def open_socket(self) -> FakeSocket:
        sock = FakeSocket(20000 + len(self.sockets))
        self.sockets.append(sock)
        return sock

    def request(self, host: str, port: int, payload: bytes) -> bytes:
        sock = self.open_socket()
        try:
            data = self.send_on_socket(sock, host, port, payload, receive=True)
            assert data is not None
            return data
        finally:
            sock.close()

    def send(self, host: str, port: int, payload: bytes, *, receive: bool = True) -> bytes | None:
        sock = self.open_socket()
        try:
            return self.send_on_socket(sock, host, port, payload, receive=receive)
        finally:
            sock.close()

    def send_on_socket(
        self,
        sock: FakeSocket,
        host: str,
        port: int,
        payload: bytes,
        *,
        receive: bool = True,
    ) -> bytes | None:
        head, _, body = payload.decode("utf-8", errors="replace").partition("\r\n\r\n")
        path = head.split(" ", 2)[1]
        self.requests.append((host, port, path, body))
        if not receive:
            return None
        if path.startswith("/online/p2psrv/"):
            return dh_response("<US>198.51.100.10:8800</US>")
        if path.startswith("/probe/device/"):
            return dh_response("<OK>true</OK>")
        if path.startswith("/info/device/"):
            return dh_response("<Device>demo</Device>")
        if path == "/online/relay":
            return dh_response("<Address>198.51.100.20:8800</Address>")
        if path == "/relay/agent":
            return dh_response("<Token>abc</Token><Agent>198.51.100.21:8800</Agent>")
        if path.startswith("/relay/start/"):
            return dh_response("<OK>true</OK>")
        raise AssertionError(f"unexpected Dahua path {path}")

    def receive_on_socket(self, sock: FakeSocket, host: str, port: int) -> bytes:
        if not self.async_reads:
            raise TimeoutError("no async fixture")
        return self.async_reads.pop(0)


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


def test_dahua_status_payload_includes_pubaddr_aliases() -> None:
    provider = DahuaProvider(transport=FakeDahuaTransport(), timeout=1.0)
    payload = provider.online("TEST123").to_payload()

    assert payload["ok"] is True
    assert payload["online"] is True
    assert payload["device_addr"] == "203.0.113.10:29854"
    assert payload["PubAddr"] == "203.0.113.10:29854"
    assert payload["pubaddr"] == "203.0.113.10:29854"
    assert payload["pub_addr"] == "203.0.113.10:29854"
    assert payload["pub_addr_raw"] == "203.0.113.10:29854"
    assert payload["host_ip"] == "203.0.113.10"
    assert payload["LocalAddr"] == "192.168.1.10:37777"
    assert payload["local_addr_raw"] == "192.168.1.10:37777"
