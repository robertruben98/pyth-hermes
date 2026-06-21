"""Synchronous Pyth Hermes client."""

from __future__ import annotations

import time
from decimal import Decimal
from types import TracebackType
from typing import Any, Optional

import httpx

from pyth_hermes._config import (
    _BASE_URL_UNSET,
    ClientConfig,
    resolve_base_url,
    retry_delay,
    should_retry,
    warn_if_base_url_ignored,
)
from pyth_hermes.models import PriceFeed, PriceUpdateResponse


class HermesClient:
    """Synchronous client for the Pyth Network Hermes API.

    Get a BTC/USD price in a few lines::

        from pyth_hermes import HermesClient
        client = HermesClient()
        feed_id = client.get_feed_id("Crypto.BTC/USD")
        print(client.get_price_decimal(feed_id))

    An ``api_key`` and custom ``base_url`` may be supplied for paid providers
    and for the mandatory-key requirement landing 2026-07-31.
    """

    def __init__(
        self,
        base_url: str = _BASE_URL_UNSET,
        *,
        api_key: Optional[str] = None,
        api_key_header: str = "Authorization",
        api_key_scheme: str = "Bearer",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_cap: float = 60.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        warn_if_base_url_ignored(base_url, client is not None)
        self._config = ClientConfig(
            base_url=resolve_base_url(base_url),
            api_key=api_key,
            api_key_header=api_key_header,
            api_key_scheme=api_key_scheme,
            timeout=timeout,
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_cap=backoff_cap,
        )
        self._http = client or httpx.Client(
            base_url=self._config.normalized_base_url(), timeout=timeout
        )

    @property
    def base_url(self) -> str:
        return self._config.normalized_base_url()

    def _auth_headers(self) -> dict[str, str]:
        return self._config.auth_headers()

    def __enter__(self) -> HermesClient:
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, *, params: Any = None) -> httpx.Response:
        last: Optional[httpx.Response] = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = self._http.request(
                    method, path, params=params, headers=self._auth_headers()
                )
            except httpx.TransportError:
                if attempt >= self._config.max_retries:
                    raise
                time.sleep(retry_delay(attempt, None, self._config))
                continue

            if should_retry(response) and attempt < self._config.max_retries:
                time.sleep(retry_delay(attempt, response, self._config))
                last = response
                continue
            response.raise_for_status()
            return response

        assert last is not None
        last.raise_for_status()
        return last  # pragma: no cover

    def list_price_feeds(
        self, *, query: Optional[str] = None, asset_type: Optional[str] = None
    ) -> list[PriceFeed]:
        """Return the feed catalog, optionally filtered by ``query``/``asset_type``."""
        params: dict[str, str] = {}
        if query is not None:
            params["query"] = query
        if asset_type is not None:
            params["asset_type"] = asset_type
        response = self._request("GET", "/v2/price_feeds", params=params)
        return [PriceFeed.model_validate(item) for item in response.json()]

    def get_feed_id(self, symbol: str) -> Optional[str]:
        """Resolve a canonical feed id by EXACT ``attributes.symbol`` match.

        ``/v2/price_feeds?query=...`` returns deprecated/variant feeds (MBTC,
        XBTC, ...) first and matches substrings, so we filter on an exact symbol
        equality. Returns ``None`` if no feed matches exactly.
        """
        feeds = self.list_price_feeds(query=symbol)
        for feed in feeds:
            if feed.symbol == symbol:
                return feed.id
        return None

    def get_latest_price(
        self,
        ids: list[str],
        *,
        parsed: bool = True,
        encoding: str = "hex",
    ) -> PriceUpdateResponse:
        """Latest price update for one or more feed ids."""
        params = _price_params(ids, parsed=parsed, encoding=encoding)
        response = self._request("GET", "/v2/updates/price/latest", params=params)
        return PriceUpdateResponse.model_validate(response.json())

    def get_price_at(
        self,
        publish_time: int,
        ids: list[str],
        *,
        parsed: bool = True,
        encoding: str = "hex",
    ) -> PriceUpdateResponse:
        """Historical price update at (or first after) a unix ``publish_time``."""
        params = _price_params(ids, parsed=parsed, encoding=encoding)
        response = self._request("GET", f"/v2/updates/price/{publish_time}", params=params)
        return PriceUpdateResponse.model_validate(response.json())

    def get_price_decimal(self, feed_id: str) -> Decimal:
        """Convenience: latest human-readable spot price for one feed id."""
        resp = self.get_latest_price([feed_id])
        if not resp.parsed:
            raise ValueError(f"no parsed price returned for {feed_id!r}")
        return resp.parsed[0].to_decimal()


def _price_params(ids: list[str], *, parsed: bool, encoding: str) -> list[tuple[str, str]]:
    """Build repeatable ``ids[]`` query params plus flags."""
    params: list[tuple[str, str]] = [("ids[]", fid) for fid in ids]
    params.append(("parsed", "true" if parsed else "false"))
    params.append(("encoding", encoding))
    return params
