"""
Downloads multi-ticker OHLCV and converts all prices to $/barrel.
Returns a dict of DataFrames keyed by the ticker label in config.TICKERS.
"""
import time
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

from config import TICKERS, GALLONS_PER_BARREL

warnings.filterwarnings("ignore")


def _synthetic_price(start: str, end: str, seed: int,
                     mu: float, sigma: float, theta: float) -> pd.Series:
    """Ornstein-Uhlenbeck process for synthetic oil prices."""
    rng   = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    p     = np.empty(len(dates))
    p[0]  = mu
    for i in range(1, len(dates)):
        p[i] = p[i-1] + theta * (mu - p[i-1]) + sigma * rng.standard_normal()
    return pd.Series(np.clip(p, mu * 0.3, mu * 2.5), index=dates)


_SYNTHETIC_PARAMS = {
    "CL": dict(mu=70.0, sigma=1.5, theta=0.03, seed=1),
    "BZ": dict(mu=73.0, sigma=1.6, theta=0.03, seed=2),
    "HO": dict(mu=80.0, sigma=1.8, theta=0.04, seed=3),   # already in $/bbl
    "RB": dict(mu=78.0, sigma=2.0, theta=0.04, seed=4),   # already in $/bbl
}


def fetch_all(start: str, end: str,
              retries: int = 2, delay: int = 8) -> dict[str, pd.Series]:
    """
    Returns dict: label → close price in $/barrel, aligned to common trading dates.
    """
    closes = {}
    for label, ticker in TICKERS.items():
        series = None
        for attempt in range(retries):
            try:
                raw = yf.download(ticker, start=start, end=end,
                                  auto_adjust=True, progress=False)
                if raw.empty:
                    raise ValueError("empty")
                raw.columns = raw.columns.get_level_values(0)
                series = raw["Close"].dropna()
                series.index = pd.to_datetime(series.index)
                print(f"  {label} ({ticker}): {len(series):,} bars")
                break
            except Exception as e:
                if attempt < retries - 1:
                    print(f"  {label} retry {attempt+1} ({e})…")
                    time.sleep(delay)

        if series is None or series.empty:
            print(
                f"\n  ⚠️  WARNING: {label} ({TICKERS[label]}) could not be downloaded. "
                f"Falling back to synthetic OU data — results are NOT real.\n"
                f"     Check your internet connection or try again later (Yahoo Finance "
                f"rate-limits frequent requests).\n"
            )
            series = _synthetic_price(start, end, **_SYNTHETIC_PARAMS[label])

        # Convert $/gallon → $/barrel for HO and RB
        if label in ("HO", "RB"):
            series = series * GALLONS_PER_BARREL

        closes[label] = series

    # Align to common business days
    frame = pd.DataFrame(closes).dropna()
    return {k: frame[k] for k in closes}


def log_returns(prices: dict[str, pd.Series]) -> pd.DataFrame:
    df = pd.DataFrame(prices)
    return np.log(df / df.shift(1)).dropna()
