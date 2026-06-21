from decimal import Decimal

from pyth_hermes import price_to_decimal


def test_price_to_decimal_btc_example() -> None:
    # price=6395282153102, expo=-8 -> 63952.82153102
    result = price_to_decimal(6395282153102, -8)
    assert result == Decimal("63952.82153102")
    assert isinstance(result, Decimal)


def test_price_to_decimal_positive_expo() -> None:
    assert price_to_decimal(5, 2) == Decimal("500")


def test_price_to_decimal_zero_expo() -> None:
    assert price_to_decimal(42, 0) == Decimal("42")


def test_price_to_decimal_accepts_string_price() -> None:
    # Hermes returns price as a string in JSON
    assert price_to_decimal("6395282153102", -8) == Decimal("63952.82153102")


def test_price_to_decimal_no_float_imprecision() -> None:
    # 10 ** -8 as a float would introduce error; Decimal must be exact
    assert price_to_decimal(1, -8) == Decimal("0.00000001")
