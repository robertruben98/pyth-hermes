# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-06-21

### Added
- Rich Google-style docstrings (Args/Returns/Raises, with examples) across the
  sync and async clients, response models, the retry helpers, and the pandas
  helper.
- `Field(description=...)` metadata on all response-model fields.
- `CHANGELOG.md` and `CONTRIBUTING.md`.
- README badges (CI status, PyPI version, license, supported Python versions).

### Changed
- Documentation-only release; no behavior changes.

## [0.1.0] - 2026-06-21

### Added
- Initial release.
- Synchronous `HermesClient` and asynchronous `AsyncHermesClient` over `httpx`.
- Endpoints: `GET /v2/price_feeds`, `GET /v2/updates/price/latest`,
  `GET /v2/updates/price/{publish_time}`, and the SSE
  `GET /v2/updates/price/stream` (async iterator with reconnect + backoff).
- Pydantic v2 response models and the `price_to_decimal` exponent helper
  returning an exact `Decimal`.
- `get_feed_id` resolves a canonical feed by exact `attributes.symbol`,
  avoiding deprecated `MBTC`/`XBTC` variants.
- Graceful HTTP 429 / 5xx handling: retries with exponential backoff that
  honor `Retry-After` (clamped to >= 0) and respect the 60-second rate-limit
  window.
- Configurable `base_url` and optional `api_key` (with configurable header name
  and scheme) from day one, ready for the mandatory key on 2026-07-31.
- Optional `pandas` extra with `updates_to_dataframe`.
- A `UserWarning` when both `base_url` and a custom httpx `client` are supplied
  (the former cannot take effect).
- True Python 3.9 support verified in CI (matrix 3.9-3.13).

[0.1.1]: https://github.com/robertruben98/pyth-hermes/releases/tag/v0.1.1
[0.1.0]: https://github.com/robertruben98/pyth-hermes/releases/tag/v0.1.0
