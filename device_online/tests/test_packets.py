from __future__ import annotations

from device_online.protocol.dahua_packets import DahuaPacketCodec, parse_response, tag_value
from device_online.protocol.intelbras_packets import (
    T2U_CMD_QUERY,
    T2U_CMD_QUERY_RESPONSE,
    T2U_MAGIC,
    build_query_request,
    parse_query_response,
)


def test_dahua_response_parser_and_xml_tag() -> None:
    raw = b"DHHTTP/1.1 200 OK\r\nCSeq: 1\r\n\r\n<US>127.0.0.1:8800</US>"
    parsed = parse_response(raw)
    assert parsed.code == 200
    assert parsed.headers["CSeq"] == "1"
    assert tag_value(parsed.body, "US") == "127.0.0.1:8800"


def test_dahua_request_uses_dhget_without_body() -> None:
    codec = DahuaPacketCodec("user", "key")
    raw = codec.build_request("/online/p2psrv/ABC", with_auth=False)
    assert raw.startswith(b"DHGET /online/p2psrv/ABC HTTP/1.1\r\n")
    assert b"Authorization:" not in raw


def test_intelbras_query_packet_shape() -> None:
    packet = build_query_request("TEST123")
    assert packet[:4] == T2U_MAGIC.to_bytes(2, "little") + T2U_CMD_QUERY.to_bytes(2, "little")
    assert b"TEST123\0" in packet


def test_intelbras_query_response_parser_online() -> None:
    serial = "TEST123"
    response = bytearray(0xAC)
    response[:2] = T2U_MAGIC.to_bytes(2, "little")
    response[2:4] = T2U_CMD_QUERY_RESPONSE.to_bytes(2, "little")
    response[4 : 4 + len(serial)] = serial.encode("ascii")
    response[0x68:0x6C] = (1).to_bytes(4, "little")
    addr = b"203.0.113.10:1500"
    response[0x6C : 0x6C + len(addr)] = addr

    parsed = parse_query_response(bytes(response), serial)
    assert parsed.ok is True
    assert parsed.online is True
    assert parsed.query_ret == 1
    assert parsed.device_addr == "203.0.113.10:1500"
