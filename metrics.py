"""
Performance analytics: portfolio-level and per-spread breakdown.
"""
import numpy as np
import pandas as pd
from typing import List
from backtest import Trade


def _sharpe(ret: pd.Series, rf: float = 0.05) -> float:
    ann = ret.mean() * 252
    vol = ret.std() * np.sqrt(252)
    return (ann - rf) / vol if vol > 0 else np.nan


def sharpe_float(equity: pd.Series, rf: float = 0.05) -> float:
    """Return Sharpe as a raw float — use this when you need to compare or sort."""
    return _sharpe(equity.pct_change().dropna(), rf)


def _sortino(ret: pd.Series, rf: float = 0.05) -> float:
    ann  = ret.mean() * 252
    down = ret[ret < 0]
    dvol = down.std() * np.sqrt(252) if len(down) > 0 else np.nan
    return (ann - rf) / dvol if dvol and dvol > 0 else np.nan


def _max_dd(equity: pd.Series) -> float:
    return float(((equity - equity.cummax()) / equity.cummax()).min())


def _dd_series(equity: pd.Series) -> pd.Series:
    return (equity - equity.cummax()) / equity.cummax()


def portfolio_stats(equity: pd.Series, trades: List[Trade],
                    rf: float = 0.05) -> dict:
    ret       = equity.pct_change().dropna()
    n_years   = len(ret) / 252
    total_ret = equity.iloc[-1] / equity.iloc[0] - 1
    ann_ret   = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else np.nan
    ann_vol   = ret.std() * np.sqrt(252)
    max_dd    = _max_dd(equity)

    pnls   = [t.pnl_net for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) if pnls else np.nan
    pf = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else np.nan

    avg_hold = np.mean([t.hold_days for t in trades if t.hold_days is not None]) if trades else np.nan
    stop_rate = sum(1 for t in trades if t.stopped_out) / len(trades) if trades else np.nan
    total_cost = sum(t.cost for t in trades)

    return {
        "Total Return":      f"{total_ret:.2%}",
        "Ann. Return":       f"{ann_ret:.2%}",
        "Ann. Volatility":   f"{ann_vol:.2%}",
        "Sharpe Ratio":      f"{_sharpe(ret, rf):.2f}",
        "Sortino Ratio":     f"{_sortino(ret, rf):.2f}",
        "Max Drawdown":      f"{max_dd:.2%}",
        "Calmar Ratio":      f"{ann_ret / abs(max_dd):.2f}" if max_dd != 0 else "n/a",
        "Total Trades":      len(trades),
        "Win Rate":          f"{win_rate:.2%}",
        "Profit Factor":     f"{pf:.2f}",
        "Avg Hold (days)":   f"{avg_hold:.1f}",
        "Stop-out Rate":     f"{stop_rate:.2%}",
        "Total Costs ($)":   f"{total_cost:,.0f}",
    }


def per_spread_stats(trades: List[Trade]) -> pd.DataFrame:
    """Break down P&L and trade count by spread."""
    rows = []
    names = sorted({t.spread_name for t in trades})
    for name in names:
        sub    = [t for t in trades if t.spread_name == name]
        pnls   = [t.pnl_net for t in sub]
        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        rows.append({
            "spread":    name,
            "n_trades":  len(sub),
            "total_pnl": round(sum(pnls), 0),
            "win_rate":  round(len(wins) / len(pnls), 3) if pnls else 0,
            "avg_pnl":   round(np.mean(pnls), 0) if pnls else 0,
            "avg_win":   round(np.mean(wins), 0) if wins else 0,
            "avg_loss":  round(np.mean(losses), 0) if losses else 0,
            "pf":        round(abs(sum(wins) / sum(losses)), 2)
                         if losses and sum(losses) != 0 else np.nan,
        })
    return pd.DataFrame(rows).sort_values("total_pnl", ascending=False).reset_index(drop=True)


def monthly_returns(equity: pd.Series) -> pd.DataFrame:
    m  = equity.resample("ME").last().pct_change().dropna()
    m.index = m.index.to_period("M")
    df = m.to_frame("ret")
    df["year"]  = df.index.year
    df["month"] = df.index.month
    pivot = df.pivot(index="year", columns="month", values="ret")
    month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    pivot.columns = [month_names[c - 1] for c in pivot.columns]
    return pivot
