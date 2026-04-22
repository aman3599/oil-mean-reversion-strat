"""
Z-score based signal engine. Parameterised per spread.
Returns a SignalFrame with z-scores, raw signals, and ATR for stops.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

from config import (SPREADS, SpreadDef,
                    DEFAULT_LOOKBACK, DEFAULT_Z_ENTRY, DEFAULT_Z_EXIT,
                    DEFAULT_ATR_MULT, ATR_PERIOD)


@dataclass
class SpreadSignal:
    name:     str
    zscore:   pd.Series
    signal:   pd.Series   # +1 long spread, -1 short spread, 0 flat
    spread:   pd.Series   # raw spread values
    atr:      pd.Series   # ATR of the spread series
    lookback: int
    z_entry:  float
    z_exit:   float


def _zscore(series: pd.Series, window: int) -> pd.Series:
    mu  = series.rolling(window, min_periods=window // 2).mean()
    sig = series.rolling(window, min_periods=window // 2).std()
    return (series - mu) / sig.replace(0, np.nan)


def _atr_spread(series: pd.Series, period: int) -> pd.Series:
    """
    ATR-equivalent for a spread: rolling std of daily changes (no high/low).
    """
    return series.diff().abs().ewm(span=period, adjust=False).mean()


def _raw_signal(zscore: pd.Series, z_entry: float, z_exit: float) -> pd.Series:
    """
    State-machine: NaN → hold prior state.
    Entry when |z| crosses z_entry; exit when |z| falls below z_exit.
    """
    sig = pd.Series(np.nan, index=zscore.index)
    sig[zscore < -z_entry] =  1    # spread too low → buy
    sig[zscore >  z_entry] = -1    # spread too high → sell
    sig[zscore.abs() < z_exit] = 0
    return sig.ffill().fillna(0).astype(int)


def compute_signals(spreads: pd.DataFrame,
                    lookback_override: Optional[int] = None,
                    z_entry_override: Optional[float] = None,
                    z_exit_override: Optional[float] = None) -> dict[str, SpreadSignal]:
    """
    Compute z-score signals for every spread column.
    Spread-level config takes priority; CLI overrides take priority over both.
    """
    # Build a lookup from name → SpreadDef (for defined spreads)
    sd_by_name = {sd.name: sd for sd in SPREADS}
    signals = {}

    for col in spreads.columns:
        sd  = sd_by_name.get(col)
        lb  = lookback_override or (sd.lookback if sd and sd.lookback else DEFAULT_LOOKBACK)
        ze  = z_entry_override  or (sd.z_entry  if sd and sd.z_entry  else DEFAULT_Z_ENTRY)
        zx  = z_exit_override   or (sd.z_exit   if sd and sd.z_exit   else DEFAULT_Z_EXIT)

        s   = spreads[col].dropna()
        z   = _zscore(s, lb)
        raw = _raw_signal(z, ze, zx)
        atr = _atr_spread(s, ATR_PERIOD)

        signals[col] = SpreadSignal(
            name=col, zscore=z, signal=raw,
            spread=s, atr=atr,
            lookback=lb, z_entry=ze, z_exit=zx,
        )

    return signals


def zscore_heatmap_data(signals: dict[str, SpreadSignal]) -> pd.DataFrame:
    """Wide DataFrame of z-scores for heatmap visualisation."""
    return pd.DataFrame({k: v.zscore for k, v in signals.items()})
