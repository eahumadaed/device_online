# Device Online Providers

Unified Python providers for checking DVR/NVR P2P online status across multiple
vendors through a common API.

The library currently includes provider adapters for:

- Dahua-compatible cloud checks.
- Intelbras-compatible direct T2U checks.

This repository does not include vendor SDKs, DLLs, real device serials, packet
captures, private endpoint pools, or production configuration.

## Install

```bash
python -m pip install -r requirements.txt
```

For local development without packaging:

```bash
set PYTHONPATH=%CD%
```

On Linux/macOS:

```bash
export PYTHONPATH="$PWD"
```

## Usage

```python
from device_online import get_provider

provider = get_provider("dahua")
status = provider.online("DEMO123456789")
print(status.to_payload())
```

Vendor selection is explicit:

```python
dahua = get_provider("dahua")
intelbras = get_provider("intelbras")
```

## API server

```bash
python -m device_online.api.server
```

Routes:

- `GET /health`
- `GET /vendors`
- `GET /online/{serial}`
- `GET /online/{vendor}/{serial}`

`/online/{serial}` uses `DEVICE_VENDOR`; the default is `dahua`.

## Configuration

All operational values are provided through environment variables. Do not commit
real credentials, endpoint pools, captures, serial lists, SDKs, or DLLs.

Common settings:

- `DEVICE_VENDOR`: default API vendor, usually `dahua`.
- `API_BIND`: HTTP bind address, for example `127.0.0.1:9165`.
- `UDP_API_BIND`: UDP bind address, for example `127.0.0.1:9166`.
- `ONLINE_MAX_CONCURRENT`: maximum concurrent checks.
- `ONLINE_WAIT_TIMEOUT_SECS`: wait time for a concurrency slot.

Dahua settings:

- `DH_MAIN_SERVER`, defaults to `www.easy4ipcloud.com`.
- `DH_MAIN_PORT`
- `DH_MAIN_SERVER_IPS`, optional comma-separated resolver hints. Do not commit real private pools.
- `DH_USERNAME`
- `DH_USERKEY`
- `DH_UDP_TIMEOUT_SECS`

Intelbras settings:

- `T2U_QUERY_SERVERS`, defaults to `intelbrasp2p.com.br:1250`.
- `T2U_LOGIN_PACKET_HEX`, optional override for the built-in login packet.
- `T2U_DIRECT_TIMEOUT_SECS`

Use documentation/example values only in public material, such as
`203.0.113.10:1250`, `DEMO123456789`, or `example-token`.

## Tests

```bash
set PYTHONPATH=%CD%
python -m pytest device_online\tests -q
```

The included tests use synthetic fixtures only.
