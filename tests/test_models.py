from decimal import Decimal

from pyth_hermes import (
    ParsedPriceUpdate,
    PriceFeed,
    PriceUpdateResponse,
)

LATEST_RESPONSE = {
    "binary": {
        "encoding": "hex",
        "data": ["504e41550100000000a001..."],
    },
    "parsed": [
        {
            "id": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
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
            "metadata": {
                "slot": 12345,
                "proof_available_time": 1718900001,
                "prev_publish_time": 1718899999,
            },
        }
    ],
}


def test_parse_price_update_response() -> None:
    resp = PriceUpdateResponse.model_validate(LATEST_RESPONSE)
    assert resp.binary.encoding == "hex"
    assert resp.binary.data == ["504e41550100000000a001..."]
    assert resp.parsed is not None
    assert len(resp.parsed) == 1


def test_parsed_update_price_is_decimal() -> None:
    resp = PriceUpdateResponse.model_validate(LATEST_RESPONSE)
    assert resp.parsed is not None
    update = resp.parsed[0]
    assert update.id == "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
    assert update.price.expo == -8
    assert update.to_decimal() == Decimal("63952.82153102")


def test_parsed_update_metadata_optional_fields() -> None:
    update = ParsedPriceUpdate.model_validate(
        {
            "id": "abc",
            "price": {"price": "1", "conf": "1", "expo": 0, "publish_time": 1},
            "ema_price": {"price": "1", "conf": "1", "expo": 0, "publish_time": 1},
            "metadata": {},
        }
    )
    assert update.metadata.slot is None
    assert update.metadata.prev_publish_time is None


def test_parsed_can_be_null_when_parsed_false() -> None:
    resp = PriceUpdateResponse.model_validate(
        {"binary": {"encoding": "base64", "data": ["UE5BVQ=="]}, "parsed": None}
    )
    assert resp.parsed is None
    assert resp.binary.encoding == "base64"


def test_price_feed_attributes_typed_fields() -> None:
    feed = PriceFeed.model_validate(
        {
            "id": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
            "attributes": {
                "asset_type": "Crypto",
                "base": "BTC",
                "quote_currency": "USD",
                "description": "BITCOIN / US DOLLAR",
                "display_symbol": "BTC/USD",
                "symbol": "Crypto.BTC/USD",
                "schedule": "America/New_York;O,O,O,O,O,O,O;",
            },
        }
    )
    assert feed.symbol == "Crypto.BTC/USD"
    assert feed.attributes.base == "BTC"
    assert feed.attributes.quote_currency == "USD"


def test_price_feed_preserves_unknown_attributes() -> None:
    feed = PriceFeed.model_validate(
        {"id": "x", "attributes": {"symbol": "Crypto.FOO/USD", "weird_key": "v"}}
    )
    # extra="allow" keeps unknown keys accessible via the pydantic extras dict
    assert feed.attributes.model_extra is not None
    assert feed.attributes.model_extra["weird_key"] == "v"
