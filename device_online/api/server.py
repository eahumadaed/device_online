from __future__ import annotations

import json
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from ..models.response import utc_now_iso
from ..providers import get_provider


API_BIND = os.getenv("API_BIND", "0.0.0.0:9165")
UDP_API_BIND = os.getenv("UDP_API_BIND", "0.0.0.0:9166")
DEFAULT_VENDOR = os.getenv("DEVICE_VENDOR", "dahua")
ONLINE_MAX_CONCURRENT = int(os.getenv("ONLINE_MAX_CONCURRENT", "64"))
ONLINE_WAIT_TIMEOUT_SECS = float(os.getenv("ONLINE_WAIT_TIMEOUT_SECS", "30.0"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "warning")

_online_gate = threading.BoundedSemaphore(max(ONLINE_MAX_CONCURRENT, 1))

app = FastAPI(title="Unified Device Online API", docs_url=None, redoc_url=None)


def parse_bind(value: str) -> Tuple[str, int]:
    host, port = value.rsplit(":", 1)
    return host, int(port)


def online_payload(serial: str, vendor: str = DEFAULT_VENDOR) -> tuple[int, dict]:
    clean = str(serial or "").strip()
    if not clean:
        return 400, {"ok": False, "vendor": vendor, "serial": "", "online": False, "error": "missing serial"}

    acquired = _online_gate.acquire(timeout=ONLINE_WAIT_TIMEOUT_SECS)
    if not acquired:
        return 503, {
            "ok": False,
            "vendor": vendor,
            "serial": clean,
            "online": False,
            "error": "timeout waiting for online concurrency slot",
            "checked_at": utc_now_iso(),
        }

    try:
        provider = get_provider(vendor)
        status = provider.online(clean)
        return 200 if status.ok else 500, status.to_payload()
    except ValueError as exc:
        return 400, {
            "ok": False,
            "vendor": vendor,
            "serial": clean,
            "online": False,
            "error": str(exc),
            "checked_at": utc_now_iso(),
        }
    finally:
        _online_gate.release()


@app.get("/health")
def health():
    return {
        "ok": True,
        "default_vendor": DEFAULT_VENDOR,
        "vendors": ["dahua", "intelbras"],
        "checked_at": utc_now_iso(),
    }


@app.get("/vendors")
def vendors():
    return {"default": DEFAULT_VENDOR, "vendors": ["dahua", "intelbras"]}


@app.get("/online/{serial}")
def online_default(serial: str, vendor: str = Query(DEFAULT_VENDOR)):
    status_code, payload = online_payload(serial, vendor)
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/online/{vendor}/{serial}")
def online_vendor(vendor: str, serial: str):
    status_code, payload = online_payload(serial, vendor)
    return JSONResponse(status_code=status_code, content=payload)


def process_udp_request(sock: socket.socket, data: bytes, addr: tuple) -> None:
    text = data.decode("utf-8", errors="ignore").strip()
    vendor = DEFAULT_VENDOR
    serial = text
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            vendor = str(payload.get("vendor") or DEFAULT_VENDOR)
            serial = str(payload.get("serial") or "")
    except ValueError:
        if "/" in text:
            candidate_vendor, candidate_serial = text.split("/", 1)
            vendor = candidate_vendor or DEFAULT_VENDOR
            serial = candidate_serial

    status_code, payload = online_payload(serial, vendor)
    payload["http_status_equivalent"] = status_code
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendto(raw, addr)


def udp_server_worker(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        print(f"UNIFIED_UDP_API listening on {host}:{port}", flush=True)
        with ThreadPoolExecutor(max_workers=ONLINE_MAX_CONCURRENT) as executor:
            while True:
                data, addr = sock.recvfrom(4096)
                executor.submit(process_udp_request, sock, data, addr)


def main() -> None:
    udp_host, udp_port = parse_bind(UDP_API_BIND)
    udp_thread = threading.Thread(
        target=udp_server_worker,
        args=(udp_host, udp_port),
        name="Unified-Device-Online-UDP-API",
        daemon=True,
    )
    udp_thread.start()

    api_host, api_port = parse_bind(API_BIND)
    uvicorn.run(app, host=api_host, port=api_port, log_level=LOG_LEVEL)


if __name__ == "__main__":
    main()
