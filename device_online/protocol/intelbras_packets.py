from __future__ import annotations

import os
import struct
import time
from dataclasses import asdict, dataclass


DEFAULT_QUERY_SERVERS = os.getenv(
    "T2U_QUERY_SERVERS",
    "intelbrasp2p.com.br:1250",
)

T2U_MAGIC = 0x2012
T2U_CMD_SERVER_LIST = 0x1389
T2U_CMD_SERVER_LIST_RESPONSE = 0x138A
T2U_CMD_LOGIN = 0x03F4
T2U_CMD_LOGIN_RESPONSE = 0x03F5
T2U_CMD_QUERY = 0x03F2
T2U_CMD_QUERY_RESPONSE = 0x03F3

LOGIN_PACKET = bytes.fromhex(
    os.getenv(
        "T2U_LOGIN_PACKET_HEX",
        "1220f403aa5a6c6a01007e3501009235a94d40b78a537de63e177ba2ba70"
        "aa2b0755d04688da82cbdecce7897cb07ab3303534646664353338646531"
        "616436633232376537656435323765326137640000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000790000000400000003000000",
    )
)

QUERY_TAIL = bytes.fromhex(
    "004001000000501c0080010000007ce7028001000000000000000000000001"
    "00000000000000000000000000000034d0c07b000000009985c57b00000000"
    "0000000000000000000000000000000028f6310000000000"
)


@dataclass
class T2uBootstrapHeader:
    magic: int
    command: int
    timestamp: int
    raw_fields: list[int]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class T2uQueryResponse:
    ok: bool
    serial: str
    online: bool
    query_ret: int | None
    device_addr: str | None
    response_hex_prefix: str


def build_server_list_request(now: int | None = None) -> bytes:
    ts = int(time.time()) if now is None else int(now)
    return struct.pack("<HHIHHI", T2U_MAGIC, T2U_CMD_SERVER_LIST, ts, 1, 0x32, 1)


def parse_header(data: bytes) -> T2uBootstrapHeader:
    if len(data) < 16:
        raise ValueError(f"short t2u response: {len(data)} bytes")
    magic, command, timestamp, field_a, field_b, field_c = struct.unpack("<HHIHHI", data[:16])
    return T2uBootstrapHeader(magic, command, timestamp, [field_a, field_b, field_c])


def parse_query_servers(value: str = DEFAULT_QUERY_SERVERS) -> list[tuple[str, int]]:
    servers: list[tuple[str, int]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        host, raw_port = item.rsplit(":", 1)
        servers.append((host, int(raw_port)))
    return servers


def build_query_request(serial: str) -> bytes:
    clean = serial.strip().encode("ascii", errors="ignore")
    if not clean:
        raise ValueError("serial is required")
    return struct.pack("<HH", T2U_MAGIC, T2U_CMD_QUERY) + clean + b"\0" + QUERY_TAIL


def parse_query_response(data: bytes, expected_serial: str) -> T2uQueryResponse:
    if len(data) < 112:
        raise ValueError(f"short query response: {len(data)} bytes")
    magic, command = struct.unpack("<HH", data[:4])
    if magic != T2U_MAGIC or command != T2U_CMD_QUERY_RESPONSE:
        raise ValueError(f"unexpected query response header magic=0x{magic:04x} command=0x{command:04x}")

    echoed = data[4:68].split(b"\0", 1)[0].decode("ascii", errors="replace")
    if echoed != expected_serial:
        raise ValueError(f"query response serial mismatch: {echoed!r} != {expected_serial!r}")

    flag = int.from_bytes(data[0x68:0x6C], "little")
    addr = data[0x6C:0xAC].split(b"\0", 1)[0].decode("ascii", errors="replace")
    online = flag == 1 and bool(addr)
    return T2uQueryResponse(
        ok=True,
        serial=expected_serial,
        online=online,
        query_ret=1 if online else 0,
        device_addr=addr or None,
        response_hex_prefix=data[:160].hex(),
    )
