"""Stream live BTC/USD price updates via SSE with automatic reconnect.

Run: python examples/stream_prices.py  (Ctrl-C to stop)
"""

from __future__ import annotations

import asyncio

from pyth_hermes import AsyncHermesClient

BTC_ID = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"


async def main() -> None:
    async with AsyncHermesClient() as client:
        count = 0
        async for update in client.stream_prices([BTC_ID]):
            if not update.parsed:
                continue
            price = update.parsed[0]
            print(f"BTC/USD = ${price.to_decimal():,.2f}  @ {price.price.publish_time}")
            count += 1
            if count >= 5:  # demo: stop after 5 ticks
                break


if __name__ == "__main__":
    asyncio.run(main())
