"""Get the latest canonical BTC/USD price from Hermes (production, no auth today).

Run: python examples/get_btc_price.py
"""

from __future__ import annotations

from pyth_hermes import HermesClient


def main() -> None:
    with HermesClient() as client:
        feed_id = client.get_feed_id("Crypto.BTC/USD")
        if feed_id is None:
            raise SystemExit("BTC/USD feed not found")
        print(f"Crypto.BTC/USD feed id: {feed_id}")
        price = client.get_price_decimal(feed_id)
        print(f"BTC/USD = ${price:,.2f}")


if __name__ == "__main__":
    main()
