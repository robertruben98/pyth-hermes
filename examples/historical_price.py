"""Fetch a historical BTC/USD price at a given unix timestamp.

Run: python examples/historical_price.py
"""

from __future__ import annotations

import time

from pyth_hermes import HermesClient

BTC_ID = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"


def main() -> None:
    # one hour ago
    publish_time = int(time.time()) - 3600
    with HermesClient() as client:
        resp = client.get_price_at(publish_time, [BTC_ID])
        if not resp.parsed:
            raise SystemExit("no historical update returned")
        price = resp.parsed[0]
        print(
            f"BTC/USD around {publish_time}: "
            f"${price.to_decimal():,.2f} (published {price.price.publish_time})"
        )


if __name__ == "__main__":
    main()
