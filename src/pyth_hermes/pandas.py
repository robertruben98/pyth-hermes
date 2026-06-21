"""Optional pandas helpers. Requires the ``pandas`` extra: ``pip install pyth-hermes[pandas]``."""

from __future__ import annotations

from collections.abc import Iterable

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pandas is required for pyth_hermes.pandas; install with 'pip install pyth-hermes[pandas]'"
    ) from exc

from pyth_hermes.models import PriceUpdateResponse

_COLUMNS = ["id", "publish_time", "price", "conf", "expo", "price_decimal"]


def updates_to_dataframe(responses: Iterable[PriceUpdateResponse]) -> pd.DataFrame:
    """Flatten a sequence of price-update responses into a tidy DataFrame.

    One row per parsed update with the raw integer ``price``/``conf``/``expo``
    plus a ``price_decimal`` column carrying the human-readable ``Decimal``.
    """
    rows: list[dict[str, object]] = []
    for response in responses:
        for update in response.parsed or []:
            rows.append(
                {
                    "id": update.id,
                    "publish_time": update.price.publish_time,
                    "price": update.price.price,
                    "conf": update.price.conf,
                    "expo": update.price.expo,
                    "price_decimal": update.price.to_decimal(),
                }
            )
    return pd.DataFrame(rows, columns=_COLUMNS)
