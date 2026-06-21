"""Live integration tests against the real Hermes production API.

Skipped by default (the suite runs with ``-m 'not integration'``). Run explicitly
with: ``pytest -m integration``. These hit the public, no-auth endpoint as of
2026; an API key becomes mandatory 2026-07-31.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pyth_hermes import AsyncHermesClient, HermesClient

BTC_SYMBOL = "Crypto.BTC/USD"
BTC_ID = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"


@pytest.mark.integration
def test_live_get_btc_price() -> None:
    with HermesClient() as client:
        feed_id = client.get_feed_id(BTC_SYMBOL)
        assert feed_id == BTC_ID
        price = client.get_price_decimal(feed_id)
        assert isinstance(price, Decimal)
        assert price > 0


@pytest.mark.integration
async def test_live_stream_one_update() -> None:
    async with AsyncHermesClient() as client:
        async for update in client.stream_prices([BTC_ID], reconnect=False):
            assert update.parsed is not None
            assert update.parsed[0].to_decimal() > 0
            break
