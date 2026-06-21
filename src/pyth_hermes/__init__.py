"""pyth-hermes: a Python client for the Pyth Network Hermes price-oracle API."""

from __future__ import annotations

from pyth_hermes.async_client import AsyncHermesClient
from pyth_hermes.client import HermesClient
from pyth_hermes.models import (
    BinaryUpdate,
    FeedAttributes,
    ParsedPriceUpdate,
    PriceFeed,
    PriceFeedMetadata,
    PriceUpdateResponse,
    RpcPrice,
    price_to_decimal,
)

__all__ = [
    "AsyncHermesClient",
    "BinaryUpdate",
    "FeedAttributes",
    "HermesClient",
    "ParsedPriceUpdate",
    "PriceFeed",
    "PriceFeedMetadata",
    "PriceUpdateResponse",
    "RpcPrice",
    "price_to_decimal",
]

__version__ = "0.1.1"
