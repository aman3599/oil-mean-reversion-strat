"""
Constructs spread time series from component prices.

All spreads are expressed in $/barrel (or $/bbl-equivalent).
Calendar spreads are approximated via EMA basis since we only have
front-month continuous data.
"""
import numpy as np
import pandas as pd
from typing import Optional

from config import SPREADS, SpreadDef, INCLUDE_CALENDAR_SPREADS


def build_spread(prices: dict[str, pd.Series], sd: SpreadDef) -> pd.Series:
    """Compute spread = Σ(multiplier_i × price_i) / divisor."""
    result = None
    for key, mult in sd.legs:
        term = prices[key] * mult
        result = term if result is None else result + term
    return (result / sd.divisor).rename(sd.name)


def calendar_spread(price: pd.Series, fast: int, slow: int) -> pd.Series:
    """
    Approximate M1-M2 calendar spread as:
        EMA(fast) - EMA(slow)
    Positive → front-month premium (backwardation).
    Negative → front-month discount (contango).
    """
    return price.ewm(span=fast).mean() - price.ewm(span=slow).mean()


def build_all_spreads(prices: dict[str, pd.Series]) -> pd.DataFrame:
    """Returns a DataFrame where each column is a spread time series."""
    frames = []
    for sd in SPREADS:
        s = build_spread(prices, sd)
        frames.append(s)

    if INCLUDE_CALENDAR_SPREADS:
        for key in ("CL", "BZ"):
            label = f"cal_{key.lower()}_1m3m"
            frames.append(
                calendar_spread(prices[key], fast=21, slow=63).rename(label)
            )
            label2 = f"cal_{key.lower()}_3m6m"
            frames.append(
                calendar_spread(prices[key], fast=63, slow=126).rename(label2)
            )

    return pd.concat(frames, axis=1).dropna()


def spread_descriptive_stats(spreads: pd.DataFrame) -> pd.DataFrame:
    """Summary stats for all spreads."""
    stats = pd.DataFrame({
        "mean":   spreads.mean(),
        "std":    spreads.std(),
        "min":    spreads.min(),
        "max":    spreads.max(),
        "skew":   spreads.skew(),
        "kurt":   spreads.kurtosis(),
    })
    # Half-life via OU fit
    hl = {}
    for col in spreads.columns:
        s = spreads[col].dropna()
        lag = s.shift(1).dropna()
        y   = s.iloc[1:]
        beta = np.polyfit(lag, y - lag, 1)[0]
        hl[col] = round(-np.log(2) / beta, 1) if beta < 0 else np.nan
    stats["half_life_days"] = pd.Series(hl)
    return stats.round(3)
