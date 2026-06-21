from decimal import Decimal

import httpx
import pytest
import respx

from pyth_hermes import HermesClient

BTC_ID = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"

LATEST_JSON = {
    "binary": {"encoding": "hex", "data": ["504e4155..."]},
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
            "metadata": {"slot": 1, "proof_available_time": 2, "prev_publish_time": 3},
        }
    ],
}

# Mirrors the real /v2/price_feeds?query=btc gotcha: deprecated variants are
# returned BEFORE the canonical feed, and substrings match many entries.
FEEDS_JSON = [
    {
        "id": "deadbeef00000000000000000000000000000000000000000000000000000001",
        "attributes": {"symbol": "Crypto.MBTC/USD", "base": "MBTC", "asset_type": "Crypto"},
    },
    {
        "id": "deadbeef00000000000000000000000000000000000000000000000000000002",
        "attributes": {"symbol": "Crypto.XBTC/USD", "base": "XBTC", "asset_type": "Crypto"},
    },
    {
        "id": BTC_ID,
        "attributes": {"symbol": "Crypto.BTC/USD", "base": "BTC", "asset_type": "Crypto"},
    },
]


def test_default_base_url_is_production() -> None:
    client = HermesClient()
    assert client.base_url == "https://hermes.pyth.network"


def test_base_url_is_configurable() -> None:
    client = HermesClient(base_url="https://my.paid.provider/")
    # trailing slash normalized away
    assert client.base_url == "https://my.paid.provider"


def test_api_key_default_header_is_authorization_bearer() -> None:
    client = HermesClient(api_key="secret123")
    assert client._auth_headers() == {"Authorization": "Bearer secret123"}


def test_api_key_header_name_is_configurable() -> None:
    client = HermesClient(api_key="secret123", api_key_header="X-Api-Key", api_key_scheme="")
    assert client._auth_headers() == {"X-Api-Key": "secret123"}


def test_no_api_key_means_no_auth_header() -> None:
    client = HermesClient()
    assert client._auth_headers() == {}


@respx.mock
def test_get_latest_price() -> None:
    route = respx.get("https://hermes.pyth.network/v2/updates/price/latest").mock(
        return_value=httpx.Response(200, json=LATEST_JSON)
    )
    client = HermesClient()
    resp = client.get_latest_price([BTC_ID])
    assert route.called
    assert resp.parsed is not None
    assert resp.parsed[0].to_decimal() == Decimal("63952.82153102")
    # ids[] sent as repeatable query param
    request = route.calls.last.request
    assert f"ids%5B%5D={BTC_ID}" in str(request.url) or f"ids[]={BTC_ID}" in str(request.url)


@respx.mock
def test_get_latest_price_sends_auth_header() -> None:
    route = respx.get("https://hermes.pyth.network/v2/updates/price/latest").mock(
        return_value=httpx.Response(200, json=LATEST_JSON)
    )
    client = HermesClient(api_key="tok")
    client.get_latest_price([BTC_ID])
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"


@respx.mock
def test_get_historical_price() -> None:
    route = respx.get("https://hermes.pyth.network/v2/updates/price/1718900000").mock(
        return_value=httpx.Response(200, json=LATEST_JSON)
    )
    client = HermesClient()
    resp = client.get_price_at(1718900000, [BTC_ID])
    assert route.called
    assert resp.parsed is not None


@respx.mock
def test_list_price_feeds() -> None:
    respx.get("https://hermes.pyth.network/v2/price_feeds").mock(
        return_value=httpx.Response(200, json=FEEDS_JSON)
    )
    client = HermesClient()
    feeds = client.list_price_feeds(query="btc", asset_type="crypto")
    assert len(feeds) == 3
    assert feeds[2].symbol == "Crypto.BTC/USD"


@respx.mock
def test_get_feed_id_matches_exact_symbol_not_substring() -> None:
    # query=btc returns MBTC and XBTC first; must return the EXACT Crypto.BTC/USD id.
    respx.get("https://hermes.pyth.network/v2/price_feeds").mock(
        return_value=httpx.Response(200, json=FEEDS_JSON)
    )
    client = HermesClient()
    feed_id = client.get_feed_id("Crypto.BTC/USD")
    assert feed_id == BTC_ID


@respx.mock
def test_get_feed_id_returns_none_when_no_exact_match() -> None:
    respx.get("https://hermes.pyth.network/v2/price_feeds").mock(
        return_value=httpx.Response(200, json=FEEDS_JSON)
    )
    client = HermesClient()
    assert client.get_feed_id("Crypto.DOESNOTEXIST/USD") is None


@respx.mock
def test_429_is_retried_then_succeeds() -> None:
    route = respx.get("https://hermes.pyth.network/v2/updates/price/latest")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json=LATEST_JSON),
    ]
    # tiny backoff so the test is fast; respects Retry-After when present
    client = HermesClient(max_retries=3, backoff_base=0.0, backoff_cap=0.0)
    resp = client.get_latest_price([BTC_ID])
    assert resp.parsed is not None
    assert route.call_count == 2


@respx.mock
def test_429_exhausts_retries_raises() -> None:
    respx.get("https://hermes.pyth.network/v2/updates/price/latest").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )
    client = HermesClient(max_retries=2, backoff_base=0.0, backoff_cap=0.0)
    with pytest.raises(httpx.HTTPStatusError):
        client.get_latest_price([BTC_ID])


@respx.mock
def test_5xx_is_retried() -> None:
    route = respx.get("https://hermes.pyth.network/v2/updates/price/latest")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json=LATEST_JSON),
    ]
    client = HermesClient(max_retries=3, backoff_base=0.0, backoff_cap=0.0)
    resp = client.get_latest_price([BTC_ID])
    assert resp.parsed is not None
    assert route.call_count == 2


@respx.mock
def test_get_latest_price_decimal_convenience() -> None:
    respx.get("https://hermes.pyth.network/v2/updates/price/latest").mock(
        return_value=httpx.Response(200, json=LATEST_JSON)
    )
    client = HermesClient()
    price = client.get_price_decimal(BTC_ID)
    assert price == Decimal("63952.82153102")


def test_client_is_context_manager() -> None:
    with HermesClient() as client:
        assert isinstance(client, HermesClient)
