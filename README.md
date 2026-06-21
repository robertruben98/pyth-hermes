# pyth-hermes

A typed Python client for the [Pyth Network](https://pyth.network) **Hermes** price-oracle API. Sync **and** async clients, Pydantic v2 models, Server-Sent-Events price streaming with auto-reconnect, and a `Decimal` price helper.

- Sync (`HermesClient`) and async (`AsyncHermesClient`) APIs over `httpx`
- SSE streaming with reconnect + backoff
- Graceful 429 rate-limit handling (retries that respect the 60s window)
- Configurable `base_url` (production, beta, or paid providers) and optional API key from day one
- `mypy --strict` clean, fully type-hinted, ships `py.typed`

## Install

```bash
pip install pyth-hermes
# with the optional pandas helper:
pip install "pyth-hermes[pandas]"
```

## Quickstart — BTC/USD price in under 5 lines

```python
from pyth_hermes import HermesClient

client = HermesClient()
feed_id = client.get_feed_id("Crypto.BTC/USD")   # exact-symbol lookup
print(client.get_price_decimal(feed_id))         # -> Decimal("63952.82...")
```

### Async + streaming

```python
import asyncio
from pyth_hermes import AsyncHermesClient

BTC = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"

async def main():
    async with AsyncHermesClient() as client:
        async for update in client.stream_prices([BTC]):
            print(update.parsed[0].to_decimal())

asyncio.run(main())
```

### Historical price

```python
resp = client.get_price_at(1718900000, [BTC])   # unix timestamp
print(resp.parsed[0].to_decimal())
```

### pandas

```python
from pyth_hermes.pandas import updates_to_dataframe
df = updates_to_dataframe([client.get_latest_price([BTC])])
```

## Prices and exponents

Pyth returns integer prices plus an exponent. The real value is `price * 10**expo`, computed exactly as a `Decimal`:

```python
from pyth_hermes import price_to_decimal
price_to_decimal(6395282153102, -8)   # Decimal("63952.82153102")
```

`RpcPrice.to_decimal()` and `ParsedPriceUpdate.to_decimal()` are convenience wrappers.

## Finding feed ids — use the EXACT symbol

`/v2/price_feeds?query=btc` returns **deprecated / variant** feeds (e.g. `MBTC`, `XBTC`) *before* the canonical one and matches substrings. `get_feed_id()` therefore matches on exact `attributes.symbol`:

```python
client.get_feed_id("Crypto.BTC/USD")
# -> "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
```

## 🔴 Authentication (changes 2026-07-31)

Today the public endpoint needs **no** API key. **From 2026-07-31 an API key becomes mandatory.** This client accepts one from day one — pass it now to be ready:

```python
client = HermesClient(api_key="YOUR_KEY")  # default: Authorization: Bearer YOUR_KEY
```

The exact header is not finalized publicly, so both the header name and scheme are configurable:

```python
HermesClient(api_key="KEY", api_key_header="X-Api-Key", api_key_scheme="")  # -> X-Api-Key: KEY
```

## Endpoints / base URLs

```python
from pyth_hermes import HermesClient

HermesClient()                                           # production: https://hermes.pyth.network
HermesClient(base_url="https://hermes-beta.pyth.network")  # beta
HermesClient(base_url="https://your-paid-provider.example")  # Triton / P2P / extrnode / Liquify
```

## Rate limits

The public endpoint allows **10 requests / 10 seconds per IP**. Exceeding it returns HTTP 429 for the next 60 seconds. The client retries 429 and 5xx responses with exponential backoff + jitter, honoring any `Retry-After` header and never exceeding the 60s rate-limit window per delay. Tune via `max_retries`, `backoff_base`, `backoff_cap`.

## Not implemented

The TWAP endpoints (`/v2/updates/twap/...`) are intentionally omitted — the API returns HTTP 400 "deprecated and no longer available".

## Development

```bash
pip install -e ".[dev]"
pytest                 # unit tests (no network)
pytest -m integration  # live smoke tests against production
mypy
ruff check .
```

## License

MIT
