from __future__ import annotations

import argparse

from device_online import get_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a device serial through a unified provider.")
    parser.add_argument("serial")
    parser.add_argument("--vendor", default="dahua", choices=["dahua", "intelbras"])
    args = parser.parse_args()

    provider = get_provider(args.vendor)
    print(provider.online(args.serial).to_payload())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
