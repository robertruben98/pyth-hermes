"""Shared configuration, constants and retry helpers."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

import httpx

PRODUCTION_URL = "https://hermes.pyth.network"
BETA_URL = "https://hermes-beta.pyth.network"

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
        return self.base_url.rstrip("/")

    def auth_headers(self) -> dict[str, str]:
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
            return min(float(response.headers["Retry-After"]), config.backoff_cap)
        except ValueError:
            pass

    exp = config.backoff_base * (2**attempt)
    cap = config.backoff_cap
    if response is not None and response.status_code == 429:
        cap = min(cap, RATE_LIMIT_WINDOW_SECONDS)
    return min(cap, random.uniform(0, exp)) if exp > 0 else 0.0


def should_retry(response: httpx.Response) -> bool:
    return response.status_code in RETRY_STATUS_CODES
