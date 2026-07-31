from __future__ import annotations

import base64
import hashlib
import random
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count


@dataclass
class DahuaDhResponse:
    code: int
    status: str
    headers: dict[str, str]
    body: str


class DahuaPacketCodec:
    def __init__(self, username: str, userkey: str) -> None:
        self.username = username
        self.userkey = userkey
        self._cseq = count(1)
        self._lock = threading.Lock()

    def next_cseq(self) -> int:
        with self._lock:
            return next(self._cseq)

    def build_request(self, path: str, body: str = "", *, with_auth: bool = True) -> bytes:
        method = "DHPOST" if body else "DHGET"
        nonce = random.randrange(0, 2**31)
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        password = f"{nonce}{created}DHP2P:{self.username}:{self.userkey}"
        digest = base64.b64encode(hashlib.sha1(password.encode("utf-8")).digest()).decode("ascii")

        lines = [
            f"{method} {path} HTTP/1.1",
            f"CSeq: {self.next_cseq()}",
        ]
        if with_auth:
            lines.append('Authorization: WSSE profile="UsernameToken"')
            lines.append(
                f'X-WSSE: UsernameToken Username="{self.username}", '
                f'PasswordDigest="{digest}", Nonce="{nonce}", Created="{created}"'
            )
        if body:
            lines.append("Content-Type: ")
            lines.append(f"Content-Length: {len(body.encode('utf-8'))}")

        return ("\r\n".join(lines) + "\r\n\r\n" + body).encode("utf-8")


def parse_response(raw: bytes) -> DahuaDhResponse:
    text = raw.decode("utf-8", errors="replace")
    if "\r\n\r\n" not in text:
        raise ValueError("invalid response format")

    head, body = text.split("\r\n\r\n", 1)
    lines = head.splitlines()
    if not lines:
        raise ValueError("empty response")

    parts = lines[0].split(" ", 2)
    if len(parts) < 2:
        raise ValueError("missing status code")

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key] = value

    return DahuaDhResponse(
        code=int(parts[1]),
        status=parts[2] if len(parts) > 2 else "UNKNOWN",
        headers=headers,
        body=body,
    )


def tag_value(xml: str, tag: str) -> str | None:
    match = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", xml, re.DOTALL)
    return match.group(1) if match else None


def split_host_port(value: str) -> tuple[str, int]:
    if ":" not in value:
        raise ValueError(f"invalid endpoint: {value}")
    host, port = value.rsplit(":", 1)
    return host, int(port)
