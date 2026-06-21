"""Asynchronous Pyth Hermes client with SSE price streaming."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from types import TracebackType
from typing import Any, Optional

import httpx
from httpx_sse import aconnect_sse

from pyth_hermes._config import (
    _BASE_URL_UNSET,
    ClientConfig,
    resolve_base_url,
    retry_delay,
    should_retry,
    warn_if_base_url_ignored,
)
from pyth_hermes.client import _price_params
from pyth_hermes.models import PriceFeed, PriceUpdateResponse


class AsyncHermesClient:
    """Asynchronous client for the Pyth Network Hermes API.

    Adds :meth:`stream_prices`, an async iterator over the SSE price stream with
    automatic reconnect + backoff. Mirrors :class:`~pyth_hermes.HermesClient`
    for the request/response endpoints, and is an async context manager::

        async with AsyncHermesClient() as client:
            price = await client.get_price_decimal(feed_id)

    As with the sync client, transient failures (429/5xx) are retried with
    exponential backoff that honors ``Retry-After`` and the 60-second
    rate-limit window.
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
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """Construct an asynchronous Hermes client.

        Args:
            base_url: API base URL. Defaults to production
                (``https://hermes.pyth.network``). Set to the beta host or a
                paid provider's URL as needed. Ignored (with a ``UserWarning``)
                when ``client`` is supplied.
            api_key: Optional API key. Optional today; mandatory for all callers
                from 2026-07-31. Sent on every request as a header.
            api_key_header: Header name to carry the API key. Defaults to
                ``"Authorization"``.
            api_key_scheme: Auth scheme prefix for the header value. Defaults to
                ``"Bearer"``. Pass an empty string to send the raw key.
            timeout: Per-request timeout in seconds.
            max_retries: Maximum retry attempts for transient errors, in
                addition to the initial attempt.
            backoff_base: Base seconds for exponential backoff between retries.
            backoff_cap: Maximum seconds any single backoff delay may reach.
            client: Optional preconfigured :class:`httpx.AsyncClient`. When
                given, set ``base_url`` on the client itself; the constructor's
                ``base_url`` is then ignored.

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
        self._http = client or httpx.AsyncClient(
            base_url=self._config.normalized_base_url(), timeout=timeout
        )

    @property
    def base_url(self) -> str:
        """The normalized API base URL in use (no trailing slash)."""
        return self._config.normalized_base_url()

    def _auth_headers(self) -> dict[str, str]:
        return self._config.auth_headers()

    async def __aenter__(self) -> AsyncHermesClient:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying async HTTP connection pool.

        Called automatically when the client is used as an async context
        manager.
        """
        await self._http.aclose()

    async def _request(self, method: str, path: str, *, params: Any = None) -> httpx.Response:
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._http.request(
                    method, path, params=params, headers=self._auth_headers()
                )
            except httpx.TransportError:
                if attempt >= self._config.max_retries:
                    raise
                await asyncio.sleep(retry_delay(attempt, None, self._config))
                continue

            if should_retry(response) and attempt < self._config.max_retries:
                await asyncio.sleep(retry_delay(attempt, response, self._config))
                continue
            response.raise_for_status()
            return response

        raise RuntimeError("unreachable")  # pragma: no cover

    async def list_price_feeds(
        self, *, query: Optional[str] = None, asset_type: Optional[str] = None
    ) -> list[PriceFeed]:
        """List the price-feed catalog, optionally filtered.

        Async counterpart of :meth:`~pyth_hermes.HermesClient.list_price_feeds`.
        Calls ``GET /v2/price_feeds``; the search is fuzzy, so prefer
        :meth:`get_feed_id` to resolve a single canonical feed.

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
        response = await self._request("GET", "/v2/price_feeds", params=params)
        return [PriceFeed.model_validate(item) for item in response.json()]

    async def get_feed_id(self, symbol: str) -> Optional[str]:
        """Resolve a canonical feed id by EXACT ``attributes.symbol`` match.

        Async counterpart of :meth:`~pyth_hermes.HermesClient.get_feed_id`. The
        catalog search returns deprecated/variant feeds (``MBTC``, ``XBTC``, ...)
        and matches substrings, so this filters on exact symbol equality.

        Args:
            symbol: The canonical symbol to match exactly, e.g.
                ``"Crypto.BTC/USD"``.

        Returns:
            The 32-byte hex feed id, or ``None`` if no feed matches exactly.

        Raises:
            httpx.HTTPStatusError: If the underlying catalog request fails after
                retries are exhausted.
        """
        feeds = await self.list_price_feeds(query=symbol)
        for feed in feeds:
            if feed.symbol == symbol:
                return feed.id
        return None

    async def get_latest_price(
        self, ids: list[str], *, parsed: bool = True, encoding: str = "hex"
    ) -> PriceUpdateResponse:
        """Fetch the latest price update for one or more feed ids.

        Async counterpart of :meth:`~pyth_hermes.HermesClient.get_latest_price`.
        Calls ``GET /v2/updates/price/latest``.

        Args:
            ids: One or more 32-byte hex feed ids (sent as repeatable ``ids[]``).
            parsed: Whether to include decoded per-feed updates. When ``False``,
                only the binary payload is returned and ``parsed`` is ``None``.
            encoding: Encoding for the binary payload: ``"hex"`` or ``"base64"``.

        Returns:
            A :class:`~pyth_hermes.models.PriceUpdateResponse`.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status after
                retries are exhausted.
        """
        params = _price_params(ids, parsed=parsed, encoding=encoding)
        response = await self._request("GET", "/v2/updates/price/latest", params=params)
        return PriceUpdateResponse.model_validate(response.json())

    async def get_price_at(
        self,
        publish_time: int,
        ids: list[str],
        *,
        parsed: bool = True,
        encoding: str = "hex",
    ) -> PriceUpdateResponse:
        """Fetch a historical price update at or just after a timestamp.

        Async counterpart of :meth:`~pyth_hermes.HermesClient.get_price_at`.
        Calls ``GET /v2/updates/price/{publish_time}``; the API returns the
        first update with a publish time at or after the requested timestamp.

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
        response = await self._request("GET", f"/v2/updates/price/{publish_time}", params=params)
        return PriceUpdateResponse.model_validate(response.json())

    async def get_price_decimal(self, feed_id: str) -> Decimal:
        """Return the latest human-readable spot price for one feed id.

        Async counterpart of
        :meth:`~pyth_hermes.HermesClient.get_price_decimal`.

        Args:
            feed_id: A single 32-byte hex feed id.

        Returns:
            The latest spot price as an exact :class:`~decimal.Decimal`.

        Raises:
            ValueError: If the API returns no parsed price for ``feed_id``.
            httpx.HTTPStatusError: If the API returns a non-2xx status after
                retries are exhausted.
        """
        resp = await self.get_latest_price([feed_id])
        if not resp.parsed:
            raise ValueError(f"no parsed price returned for {feed_id!r}")
        return resp.parsed[0].to_decimal()

    async def stream_prices(
        self,
        ids: list[str],
        *,
        parsed: bool = True,
        reconnect: bool = True,
    ) -> AsyncIterator[PriceUpdateResponse]:
        """Stream live price updates over Server-Sent Events (SSE).

        Opens ``GET /v2/updates/price/stream`` and yields one
        :class:`~pyth_hermes.models.PriceUpdateResponse` per event. With
        ``reconnect=True`` (the default) the stream transparently re-opens after
        a disconnect or transient error, applying exponential backoff between
        attempts (the backoff counter resets after each successful connect). With
        ``reconnect=False`` the iterator stops when the server closes the stream
        and re-raises transport/HTTP errors.

        Args:
            ids: One or more 32-byte hex feed ids to subscribe to (sent as
                repeatable ``ids[]``).
            parsed: Whether each event should include decoded per-feed updates.
            reconnect: Whether to automatically reconnect with backoff after a
                disconnect or transient error. Defaults to ``True``.

        Yields:
            A :class:`~pyth_hermes.models.PriceUpdateResponse` for each SSE event.

        Raises:
            httpx.HTTPStatusError: On a non-2xx stream response when
                ``reconnect=False``.
            httpx.TransportError: On a connection failure when
                ``reconnect=False``.

        Example:
            >>> btc = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
            >>> async with AsyncHermesClient() as client:
            ...     async for update in client.stream_prices([btc]):
            ...         if update.parsed:
            ...             print(update.parsed[0].to_decimal())
            ...             break  # stop after the first tick
        """
        params: list[tuple[str, str]] = [("ids[]", fid) for fid in ids]
        params.append(("parsed", "true" if parsed else "false"))

        attempt = 0
        while True:
            try:
                async with aconnect_sse(
                    self._http,
                    "GET",
                    "/v2/updates/price/stream",
                    params=params,
                    headers=self._auth_headers(),
                ) as event_source:
                    event_source.response.raise_for_status()
                    attempt = 0  # reset backoff after a successful connect
                    async for sse in event_source.aiter_sse():
                        if not sse.data:
                            continue
                        yield PriceUpdateResponse.model_validate_json(sse.data)
            except (httpx.TransportError, httpx.HTTPStatusError):
                if not reconnect:
                    raise
                await asyncio.sleep(retry_delay(attempt, None, self._config))
                attempt += 1
                continue

            if not reconnect:
                return
            await asyncio.sleep(retry_delay(attempt, None, self._config))
            attempt += 1
