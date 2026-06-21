from decimal import Decimal

import httpx
import pytest

from pyth_hermes import AsyncHermesClient
from pyth_hermes.models import PriceUpdateResponse

BTC_ID = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"

EVENT_JSON = (
    '{"binary":{"encoding":"hex","data":["504e41"]},'
    '"parsed":[{"id":"' + BTC_ID + '",'
    '"price":{"price":"6395282153102","conf":"3520278150","expo":-8,"publish_time":1718900000},'
    '"ema_price":{"price":"6390000000000","conf":"3500000000","expo":-8,"publish_time":1718900000},'
    '"metadata":{"slot":1,"proof_available_time":2,"prev_publish_time":3}}]}'
)


def _sse_body(n: int) -> bytes:
    return ("".join(f"data: {EVENT_JSON}\n\n" for _ in range(n))).encode()


async def test_async_get_latest_price() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "binary": {"encoding": "hex", "data": ["504e41"]},
                "parsed": [
                    {
                        "id": BTC_ID,
                        "price": {
                            "price": "6395282153102",
                            "conf": "3520278150",
                            "expo": -8,
                            "publish_time": 1718900000,
                        },
                        "ema_price": {
                            "price": "6390000000000",
                            "conf": "3500000000",
                            "expo": -8,
                            "publish_time": 1718900000,
                        },
                        "metadata": {},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://hermes.pyth.network"
    ) as http:
        client = AsyncHermesClient(client=http)
        resp = await client.get_latest_price([BTC_ID])
        assert resp.parsed is not None
        assert resp.parsed[0].to_decimal() == Decimal("63952.82153102")


async def test_stream_yields_parsed_updates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "stream" in str(request.url)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_body(3),
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://hermes.pyth.network"
    ) as http:
        client = AsyncHermesClient(client=http)
        received: list[PriceUpdateResponse] = []
        async for update in client.stream_prices([BTC_ID], reconnect=False):
            received.append(update)
        assert len(received) == 3
        assert received[0].parsed is not None
        assert received[0].parsed[0].to_decimal() == Decimal("63952.82153102")


async def test_stream_sends_ids_and_auth() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse_body(1)
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://hermes.pyth.network"
    ) as http:
        client = AsyncHermesClient(api_key="tok", client=http)
        async for _ in client.stream_prices([BTC_ID], reconnect=False):
            pass
    assert seen["auth"] == "Bearer tok"
    assert "ids%5B%5D=" + BTC_ID in str(seen["url"]) or "ids[]=" + BTC_ID in str(seen["url"])


async def test_stream_reconnects_after_disconnect() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            # first connection delivers one event then ends (server closed)
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=_sse_body(1)
            )
        # second connection delivers one more event
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse_body(1)
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://hermes.pyth.network"
    ) as http:
        client = AsyncHermesClient(client=http, backoff_base=0.0, backoff_cap=0.0)
        received: list[PriceUpdateResponse] = []
        async for update in client.stream_prices([BTC_ID], reconnect=True):
            received.append(update)
            if len(received) == 2:
                break
    assert calls["n"] == 2
    assert len(received) == 2


async def test_async_client_429_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={
                "binary": {"encoding": "hex", "data": ["x"]},
                "parsed": None,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://hermes.pyth.network"
    ) as http:
        client = AsyncHermesClient(client=http, backoff_base=0.0, backoff_cap=0.0)
        resp = await client.get_latest_price([BTC_ID])
        assert resp.parsed is None
        assert calls["n"] == 2


async def test_async_get_feed_id_exact_match() -> None:
    feeds = [
        {"id": "01", "attributes": {"symbol": "Crypto.MBTC/USD"}},
        {"id": BTC_ID, "attributes": {"symbol": "Crypto.BTC/USD"}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=feeds)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://hermes.pyth.network"
    ) as http:
        client = AsyncHermesClient(client=http)
        assert await client.get_feed_id("Crypto.BTC/USD") == BTC_ID


async def test_async_context_manager() -> None:
    async with AsyncHermesClient() as client:
        assert isinstance(client, AsyncHermesClient)


def test_async_default_base_url() -> None:
    client = AsyncHermesClient()
    assert client.base_url == "https://hermes.pyth.network"
    pytest.importorskip("httpx")
