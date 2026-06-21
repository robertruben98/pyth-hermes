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

    Adds :meth:`stream_prices`, an async iterator over the SSE price stream
    with automatic reconnect + backoff. Mirrors :class:`HermesClient` for the
    request/response endpoints.
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
        params: dict[str, str] = {}
        if query is not None:
            params["query"] = query
        if asset_type is not None:
            params["asset_type"] = asset_type
        response = await self._request("GET", "/v2/price_feeds", params=params)
        return [PriceFeed.model_validate(item) for item in response.json()]

    async def get_feed_id(self, symbol: str) -> Optional[str]:
        """Resolve a canonical feed id by EXACT ``attributes.symbol`` match."""
        feeds = await self.list_price_feeds(query=symbol)
        for feed in feeds:
            if feed.symbol == symbol:
                return feed.id
        return None

    async def get_latest_price(
        self, ids: list[str], *, parsed: bool = True, encoding: str = "hex"
    ) -> PriceUpdateResponse:
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
        params = _price_params(ids, parsed=parsed, encoding=encoding)
        response = await self._request("GET", f"/v2/updates/price/{publish_time}", params=params)
        return PriceUpdateResponse.model_validate(response.json())

    async def get_price_decimal(self, feed_id: str) -> Decimal:
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
        """Yield :class:`PriceUpdateResponse` objects from the SSE price stream.

        With ``reconnect=True`` (default) the stream transparently re-opens
        after a disconnect, applying exponential backoff between attempts. Set
        ``reconnect=False`` to stop once the server closes the connection.
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
