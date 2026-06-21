"""Shared configuration, constants and retry helpers."""

from __future__ import annotations

import random
import warnings
from dataclasses import dataclass
from typing import Optional

import httpx

PRODUCTION_URL = "https://hermes.pyth.network"
BETA_URL = "https://hermes-beta.pyth.network"

#: Sentinel for ``base_url`` so we can tell "left at default" from "explicitly
#: passed" (needed to warn when an injected client makes base_url a no-op).
_BASE_URL_UNSET = "\x00__pyth_hermes_base_url_unset__"


def warn_if_base_url_ignored(base_url: str, client_injected: bool) -> None:
    """Warn when an explicit ``base_url`` cannot take effect.

    Auth headers are applied per-request and so are honored even with a
    caller-supplied httpx client, but the request URL is resolved against that
    client's own ``base_url``. Passing both an explicit ``base_url`` and a
    ``client`` therefore silently drops the former; make that loud instead.
    """
    if client_injected and base_url is not _BASE_URL_UNSET:
        warnings.warn(
            "base_url is ignored when a custom httpx client is supplied; the "
            "request host is taken from the injected client. Set base_url on "
            "the client itself (httpx.Client(base_url=...)) or omit the client.",
            UserWarning,
            stacklevel=3,
        )


def resolve_base_url(base_url: str) -> str:
    """Map the sentinel back to the production default."""
    return PRODUCTION_URL if base_url is _BASE_URL_UNSET else base_url


# Rate limit: 10 requests / 10s per IP; exceeding -> HTTP 429 for the next 60s.
RATE_LIMIT_WINDOW_SECONDS = 60.0

#: Status codes worth retrying. 429 is rate limiting; 5xx are transient.
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ClientConfig:
    """Connection + retry settings shared by the sync and async clients."""

    base_url: str = PRODUCTION_URL
    api_key: Optional[str] = None
    api_key_header: str = "Authorization"
    api_key_scheme: str = "Bearer"
    timeout: float = 30.0
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_cap: float = 60.0

    def normalized_base_url(self) -> str:
        """Return :attr:`base_url` without any trailing slash."""
        return self.base_url.rstrip("/")

    def auth_headers(self) -> dict[str, str]:
        """Build the auth header dict for the configured API key.

        Returns:
            ``{header: "<scheme> <key>"}`` when an ``api_key`` is set (or
            ``{header: "<key>"}`` when ``api_key_scheme`` is empty), else an
            empty dict.
        """
        if not self.api_key:
            return {}
        value = (
            f"{self.api_key_scheme} {self.api_key}".strip() if self.api_key_scheme else self.api_key
        )
        return {self.api_key_header: value}


def retry_delay(attempt: int, response: Optional[httpx.Response], config: ClientConfig) -> float:
    """Compute how long to sleep before the next attempt.

    Honors a ``Retry-After`` header when present (cap-limited), otherwise uses
    exponential backoff with full jitter. For 429 responses without a header we
    do not exceed the 60s rate-limit window per delay.
    """
    if response is not None and "Retry-After" in response.headers:
        try:
            # Clamp to >= 0: a negative Retry-After would make time.sleep() raise.
            return max(0.0, min(float(response.headers["Retry-After"]), config.backoff_cap))
        except ValueError:
            pass

    exp = config.backoff_base * (2**attempt)
    cap = config.backoff_cap
    if response is not None and response.status_code == 429:
        cap = min(cap, RATE_LIMIT_WINDOW_SECONDS)
    return min(cap, random.uniform(0, exp)) if exp > 0 else 0.0


def should_retry(response: httpx.Response) -> bool:
    """Return whether a response status warrants a retry.

    Args:
        response: The HTTP response to inspect.

    Returns:
        ``True`` for retryable statuses (429 plus 500/502/503/504), else
        ``False``.
    """
    return response.status_code in RETRY_STATUS_CODES
