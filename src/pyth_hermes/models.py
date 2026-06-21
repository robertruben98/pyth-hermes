"""Pydantic v2 models for Pyth Hermes API responses."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


def price_to_decimal(price: int | str, expo: int) -> Decimal:
    """Convert a raw Pyth price + exponent into a real ``Decimal`` value.

    Real price = ``price * 10 ** expo``. Computed with ``Decimal`` to avoid
    binary float imprecision.

    Example: ``price=6395282153102, expo=-8`` -> ``Decimal("63952.82153102")``.
    """
    return Decimal(str(price)) * (Decimal(10) ** expo)


class RpcPrice(BaseModel):
    """A single price reading with its exponent and publish time."""

    model_config = ConfigDict(extra="ignore")

    price: int
    conf: int
    expo: int
    publish_time: int

    def to_decimal(self) -> Decimal:
        """Return the human-readable price as a ``Decimal``."""
        return price_to_decimal(self.price, self.expo)

    def conf_to_decimal(self) -> Decimal:
        """Return the confidence interval as a ``Decimal`` (same exponent)."""
        return price_to_decimal(self.conf, self.expo)


class PriceFeedMetadata(BaseModel):
    """Metadata attached to a parsed price update."""

    model_config = ConfigDict(extra="ignore")

    slot: Optional[int] = None
    proof_available_time: Optional[int] = None
    prev_publish_time: Optional[int] = None


class ParsedPriceUpdate(BaseModel):
    """A single parsed price update for one feed id."""

    model_config = ConfigDict(extra="ignore")

    id: str
    price: RpcPrice
    ema_price: RpcPrice
    metadata: PriceFeedMetadata = Field(default_factory=PriceFeedMetadata)

    def to_decimal(self) -> Decimal:
        """Convenience: human-readable spot price as a ``Decimal``."""
        return self.price.to_decimal()


class BinaryUpdate(BaseModel):
    """The encoded binary VAA/update payload."""

    model_config = ConfigDict(extra="ignore")

    encoding: str
    data: list[str]


class PriceUpdateResponse(BaseModel):
    """Response from the latest / historical price update endpoints."""

    model_config = ConfigDict(extra="ignore")

    binary: BinaryUpdate
    parsed: Optional[list[ParsedPriceUpdate]] = None


class FeedAttributes(BaseModel):
    """Attributes block of a price feed catalog entry.

    The Hermes ``attributes`` object is an open string map; the well-known
    keys are surfaced as typed fields and any extras are preserved.
    """

    model_config = ConfigDict(extra="allow")

    asset_type: Optional[str] = None
    base: Optional[str] = None
    quote_currency: Optional[str] = None
    country: Optional[str] = None
    description: Optional[str] = None
    display_symbol: Optional[str] = None
    publish_interval: Optional[str] = None
    schedule: Optional[str] = None
    symbol: Optional[str] = None


class PriceFeed(BaseModel):
    """A single price feed catalog entry from ``/v2/price_feeds``."""

    model_config = ConfigDict(extra="ignore")

    id: str
    attributes: FeedAttributes = Field(default_factory=FeedAttributes)

    @property
    def symbol(self) -> Optional[str]:
        """Shortcut to ``attributes.symbol`` (e.g. ``"Crypto.BTC/USD"``)."""
        return self.attributes.symbol
