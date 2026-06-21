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
    and for the mandatory-key requirement landing 2026-07-31. The client is also
    a context manager, which closes the underlying HTTP connection on exit::

        with HermesClient() as client:
            ...

    Transient failures (HTTP 429 and 5xx) are retried automatically with
    exponential backoff that honors any ``Retry-After`` header and respects the
    60-second rate-limit window.
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
        """Construct a synchronous Hermes client.

        Args:
            base_url: API base URL. Defaults to production
                (``https://hermes.pyth.network``). Set to the beta host or a
                paid provider's URL as needed. Ignored (with a ``UserWarning``)
                when ``client`` is supplied, since the request host then comes
                from the injected client.
            api_key: Optional API key. Optional today; mandatory for all callers
                from 2026-07-31. Sent on every request as a header.
            api_key_header: Header name to carry the API key. Defaults to
                ``"Authorization"``.
            api_key_scheme: Auth scheme prefix for the header value. Defaults to
                ``"Bearer"`` (producing ``Authorization: Bearer <key>``). Pass an
                empty string to send the raw key with no prefix.
            timeout: Per-request timeout in seconds.
            max_retries: Maximum retry attempts for transient errors (429/5xx and
                transport errors), in addition to the initial attempt.
            backoff_base: Base seconds for exponential backoff between retries.
            backoff_cap: Maximum seconds any single backoff delay may reach.
            client: Optional preconfigured :class:`httpx.Client` (custom
                transport, proxy, pool, ...). When given, set ``base_url`` on the
                client itself; the constructor's ``base_url`` is then ignored.

        Raises:
            UserWarning: If both an explicit ``base_url`` and ``client`` are
                passed (the former cannot take effect).
        """
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
        """The normalized API base URL in use (no trailing slash)."""
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
        """Close the underlying HTTP connection pool.

        Called automatically when the client is used as a context manager.
        """
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
        """List the price-feed catalog, optionally filtered.

        Calls ``GET /v2/price_feeds``. Note the search is fuzzy and returns
        deprecated/variant feeds; for resolving a single canonical feed prefer
        :meth:`get_feed_id`, which matches on exact symbol.

        Args:
            query: Case-insensitive substring to filter feeds by symbol.
            asset_type: Asset class filter, e.g. ``"crypto"``, ``"fx"``,
                ``"equity"``, ``"metal"``.

        Returns:
            A list of :class:`~pyth_hermes.models.PriceFeed` catalog entries.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status after
                retries are exhausted.
        """
        params: dict[str, str] = {}
        if query is not None:
            params["query"] = query
        if asset_type is not None:
            params["asset_type"] = asset_type
        response = self._request("GET", "/v2/price_feeds", params=params)
        return [PriceFeed.model_validate(item) for item in response.json()]

    def get_feed_id(self, symbol: str) -> Optional[str]:
        """Resolve a canonical feed id by EXACT ``attributes.symbol`` match.

        ``GET /v2/price_feeds?query=...`` returns deprecated/variant feeds
        (``MBTC``, ``XBTC``, ...) first and matches substrings, so this filters
        on exact symbol equality to avoid picking the wrong feed.

        Args:
            symbol: The canonical symbol to match exactly, e.g.
                ``"Crypto.BTC/USD"``.

        Returns:
            The 32-byte hex feed id, or ``None`` if no feed matches exactly.

        Raises:
            httpx.HTTPStatusError: If the underlying catalog request fails after
                retries are exhausted.

        Example:
            >>> client.get_feed_id("Crypto.BTC/USD")
            'e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43'
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
        """Fetch the latest price update for one or more feed ids.

        Calls ``GET /v2/updates/price/latest``.

        Args:
            ids: One or more 32-byte hex feed ids (sent as repeatable ``ids[]``).
            parsed: Whether to include decoded per-feed updates. When ``False``,
                only the binary payload is returned and ``parsed`` is ``None``.
            encoding: Encoding for the binary payload: ``"hex"`` or ``"base64"``.

        Returns:
            A :class:`~pyth_hermes.models.PriceUpdateResponse` with the binary
            payload and (when ``parsed``) the decoded updates.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status after
                retries are exhausted.

        Example:
            >>> btc = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
            >>> resp = client.get_latest_price([btc])
            >>> resp.parsed[0].to_decimal()
            Decimal('63952.82153102')
        """
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
        """Fetch a historical price update at or just after a timestamp.

        Calls ``GET /v2/updates/price/{publish_time}``; the API returns the
        first update with a publish time greater than or equal to the requested
        timestamp.

        Args:
            publish_time: Unix timestamp (seconds) to look up.
            ids: One or more 32-byte hex feed ids (sent as repeatable ``ids[]``).
            parsed: Whether to include decoded per-feed updates.
            encoding: Encoding for the binary payload: ``"hex"`` or ``"base64"``.

        Returns:
            A :class:`~pyth_hermes.models.PriceUpdateResponse` for that instant.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status after
                retries are exhausted.
        """
        params = _price_params(ids, parsed=parsed, encoding=encoding)
        response = self._request("GET", f"/v2/updates/price/{publish_time}", params=params)
        return PriceUpdateResponse.model_validate(response.json())

    def get_price_decimal(self, feed_id: str) -> Decimal:
        """Return the latest human-readable spot price for one feed id.

        Convenience wrapper over :meth:`get_latest_price` that returns just the
        spot price as a :class:`~decimal.Decimal`.

        Args:
            feed_id: A single 32-byte hex feed id.

        Returns:
            The latest spot price as an exact ``Decimal``.

        Raises:
            ValueError: If the API returns no parsed price for ``feed_id``.
            httpx.HTTPStatusError: If the API returns a non-2xx status after
                retries are exhausted.
        """
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
