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

    Produces one row per parsed update. Responses with ``parsed=None`` (or no
    updates) contribute no rows.

    Args:
        responses: An iterable of
            :class:`~pyth_hermes.models.PriceUpdateResponse` objects, e.g. the
            results of repeated :meth:`~pyth_hermes.HermesClient.get_price_at`
            calls for a historical series.

    Returns:
        A :class:`pandas.DataFrame` with columns ``id``, ``publish_time``,
        ``price``, ``conf``, ``expo`` (raw values) and ``price_decimal`` (the
        human-readable :class:`~decimal.Decimal`). The frame is empty (but keeps
        these columns) when no parsed updates are present.

    Raises:
        ImportError: If pandas is not installed (install the ``pandas`` extra).

    Example:
        >>> from pyth_hermes import HermesClient
        >>> from pyth_hermes.pandas import updates_to_dataframe
        >>> client = HermesClient()
        >>> btc = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
        >>> df = updates_to_dataframe([client.get_latest_price([btc])])
        >>> df["price_decimal"].iloc[0]  # doctest: +SKIP
        Decimal('63952.82153102')
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
