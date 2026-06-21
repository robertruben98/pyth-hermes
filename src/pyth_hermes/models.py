"""Pydantic v2 models for Pyth Hermes API responses.

These models mirror the JSON shapes returned by the Hermes ``/v2`` endpoints.
Every model uses ``extra="ignore"`` (forward-compatible: unknown fields the API
may add later are dropped) except :class:`FeedAttributes`, which uses
``extra="allow"`` to preserve the open-ended attribute map.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field


def price_to_decimal(price: Union[int, str], expo: int) -> Decimal:
    """Convert a raw Pyth price + exponent into a real ``Decimal`` value.

    Pyth reports prices as a large integer plus a (usually negative) base-10
    exponent. The human-readable value is ``price * 10 ** expo``, computed here
    with :class:`~decimal.Decimal` to avoid binary float imprecision.

    Args:
        price: The raw integer price, as an ``int`` or its string form (Hermes
            returns it as a JSON string).
        expo: The base-10 exponent to apply (e.g. ``-8``).

    Returns:
        The exact human-readable price as a :class:`~decimal.Decimal`.

    Example:
        >>> price_to_decimal(6395282153102, -8)
        Decimal('63952.82153102')
    """
    return Decimal(str(price)) * (Decimal(10) ** expo)


class RpcPrice(BaseModel):
    """A single price reading with its exponent and publish time.

    Used for both the spot ``price`` and the ``ema_price`` of a parsed update.
    The ``price``/``conf`` fields are raw integers; apply ``expo`` (or call
    :meth:`to_decimal` / :meth:`conf_to_decimal`) to get human-readable values.
    """

    model_config = ConfigDict(extra="ignore")

    price: int = Field(description="Raw integer price; multiply by 10**expo for the real value.")
    conf: int = Field(description="Raw integer confidence interval (same exponent as price).")
    expo: int = Field(description="Base-10 exponent applied to price and conf (often negative).")
    publish_time: int = Field(description="Unix timestamp (seconds) when this price was published.")

    def to_decimal(self) -> Decimal:
        """Return the human-readable price as a :class:`~decimal.Decimal`.

        Returns:
            ``price * 10 ** expo`` as an exact ``Decimal``.
        """
        return price_to_decimal(self.price, self.expo)

    def conf_to_decimal(self) -> Decimal:
        """Return the confidence interval as a :class:`~decimal.Decimal`.

        Uses the same exponent as the price.

        Returns:
            ``conf * 10 ** expo`` as an exact ``Decimal``.
        """
        return price_to_decimal(self.conf, self.expo)


class PriceFeedMetadata(BaseModel):
    """Metadata attached to a parsed price update.

    All fields are optional; Hermes may omit any of them depending on the
    endpoint and whether proof data is available.
    """

    model_config = ConfigDict(extra="ignore")

    slot: Optional[int] = Field(
        default=None, description="Solana slot the update was sourced from, if known."
    )
    proof_available_time: Optional[int] = Field(
        default=None, description="Unix timestamp when the cryptographic proof became available."
    )
    prev_publish_time: Optional[int] = Field(
        default=None, description="Publish time of the previous update for this feed."
    )


class ParsedPriceUpdate(BaseModel):
    """A single parsed price update for one feed id.

    Carries both the spot ``price`` and the exponentially-weighted moving
    average ``ema_price``. Call :meth:`to_decimal` for the human-readable spot
    price.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="32-byte hex feed id (no 0x prefix), e.g. 'e62df6c8...415b43'.")
    price: RpcPrice = Field(description="The current spot price reading.")
    ema_price: RpcPrice = Field(description="Exponentially-weighted moving-average price reading.")
    metadata: PriceFeedMetadata = Field(
        default_factory=PriceFeedMetadata, description="Optional slot/proof/prev-publish metadata."
    )

    def to_decimal(self) -> Decimal:
        """Return the human-readable spot price as a :class:`~decimal.Decimal`.

        Shortcut for ``self.price.to_decimal()``.
        """
        return self.price.to_decimal()


class BinaryUpdate(BaseModel):
    """The encoded binary VAA/update payload.

    This is the on-chain-submittable blob; ``data`` is a list of encoded
    strings whose representation is given by ``encoding``.
    """

    model_config = ConfigDict(extra="ignore")

    encoding: str = Field(description="Encoding of the data entries: 'hex' or 'base64'.")
    data: list[str] = Field(description="Encoded binary update payload(s), one per chunk.")


class PriceUpdateResponse(BaseModel):
    """Response from the latest / historical price update endpoints.

    Returned by ``GET /v2/updates/price/latest`` and
    ``GET /v2/updates/price/{publish_time}``, and by each SSE stream event.
    ``parsed`` is ``None`` when the request was made with ``parsed=False``.
    """

    model_config = ConfigDict(extra="ignore")

    binary: BinaryUpdate = Field(description="Encoded binary update payload (always present).")
    parsed: Optional[list[ParsedPriceUpdate]] = Field(
        default=None, description="Decoded per-feed price updates, or None when parsed=False."
    )


class FeedAttributes(BaseModel):
    """Attributes block of a price feed catalog entry.

    The Hermes ``attributes`` object is an open string map; the well-known keys
    are surfaced as typed fields and any extra keys are preserved (accessible
    via :attr:`pydantic.BaseModel.model_extra`).
    """

    model_config = ConfigDict(extra="allow")

    asset_type: Optional[str] = Field(
        default=None, description="Asset class, e.g. 'Crypto', 'FX', 'Equity'."
    )
    base: Optional[str] = Field(default=None, description="Base asset symbol, e.g. 'BTC'.")
    quote_currency: Optional[str] = Field(default=None, description="Quote currency, e.g. 'USD'.")
    country: Optional[str] = Field(
        default=None, description="Country code, for region-bound feeds."
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable description, e.g. 'BITCOIN / US DOLLAR'."
    )
    display_symbol: Optional[str] = Field(
        default=None, description="Display symbol, e.g. 'BTC/USD'."
    )
    publish_interval: Optional[str] = Field(
        default=None, description="Nominal publish interval for the feed, if specified."
    )
    schedule: Optional[str] = Field(
        default=None, description="Trading schedule string (timezone;weekly-pattern;holidays)."
    )
    symbol: Optional[str] = Field(
        default=None,
        description="Canonical symbol used for exact matching, e.g. 'Crypto.BTC/USD'.",
    )


class PriceFeed(BaseModel):
    """A single price feed catalog entry from ``GET /v2/price_feeds``."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="32-byte hex feed id (no 0x prefix).")
    attributes: FeedAttributes = Field(
        default_factory=FeedAttributes, description="Feed metadata (symbol, base, asset type, ...)."
    )

    @property
    def symbol(self) -> Optional[str]:
        """Shortcut to ``attributes.symbol`` (e.g. ``"Crypto.BTC/USD"``).

        Returns:
            The canonical symbol, or ``None`` if absent.
        """
        return self.attributes.symbol
