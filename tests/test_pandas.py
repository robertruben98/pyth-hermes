from decimal import Decimal

import pytest

from pyth_hermes import PriceUpdateResponse

pd = pytest.importorskip("pandas")

from pyth_hermes.pandas import updates_to_dataframe  # noqa: E402

BTC_ID = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"


def _resp(price: str, ts: int) -> PriceUpdateResponse:
    return PriceUpdateResponse.model_validate(
        {
            "binary": {"encoding": "hex", "data": ["x"]},
            "parsed": [
                {
                    "id": BTC_ID,
                    "price": {"price": price, "conf": "100", "expo": -8, "publish_time": ts},
                    "ema_price": {
                        "price": price,
                        "conf": "100",
                        "expo": -8,
                        "publish_time": ts,
                    },
                    "metadata": {},
                }
            ],
        }
    )


def test_updates_to_dataframe_columns_and_decimal() -> None:
    df = updates_to_dataframe([_resp("6395282153102", 1718900000)])
    assert list(df.columns) == ["id", "publish_time", "price", "conf", "expo", "price_decimal"]
    assert len(df) == 1
    assert df.iloc[0]["id"] == BTC_ID
    assert df.iloc[0]["price_decimal"] == Decimal("63952.82153102")


def test_updates_to_dataframe_multiple_rows() -> None:
    df = updates_to_dataframe([_resp("100000000", 1), _resp("200000000", 2)])
    assert len(df) == 2
    assert df.iloc[0]["price_decimal"] == Decimal("1")
    assert df.iloc[1]["price_decimal"] == Decimal("2")


def test_updates_to_dataframe_empty() -> None:
    df = updates_to_dataframe([])
    assert len(df) == 0
    assert list(df.columns) == ["id", "publish_time", "price", "conf", "expo", "price_decimal"]
