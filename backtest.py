"""
Event-driven spread backtest engine.

Each spread is traded independently. A portfolio-level loop iterates
over every bar and manages open positions, stops, and new entries
across all spreads simultaneously.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from config import DEFAULT_ATR_MULT, LOT_SIZE
from risk import (target_notional, lots_from_notional,
                  transaction_cost, gross_notional, check_capacity)
from signals import SpreadSignal


@dataclass
class Trade:
    spread_name:  str
    entry_date:   pd.Timestamp
    exit_date:    Optional[pd.Timestamp] = None
    direction:    int   = 0      # +1 long spread / -1 short spread
    notional:     float = 0.0    # USD at entry
    lots:         float = 0.0
    entry_price:  float = 0.0    # spread value at entry
    exit_price:   float = 0.0
    stop_price:   float = 0.0
    pnl:          float = 0.0    # gross
    pnl_net:      float = 0.0    # after costs
    stopped_out:  bool  = False
    cost:         float = 0.0

    def close(self, date, exit_price, stopped_out=False):
        self.exit_date   = date
        self.exit_price  = exit_price
        self.stopped_out = stopped_out
        # P&L in $/bbl × lots × bbl/lot
        self.pnl = (exit_price - self.entry_price) * self.direction * \
                   self.lots * LOT_SIZE
        self.cost    = transaction_cost(self.notional, self.lots)
        self.pnl_net = self.pnl - self.cost

    @property
    def hold_days(self) -> Optional[int]:
        if self.exit_date:
            return (self.exit_date - self.entry_date).days
        return None


def _stop_price(entry: float, atr: float, direction: int,
                mult: float = DEFAULT_ATR_MULT) -> float:
    return entry - direction * mult * atr


def run_backtest(signals: dict[str, SpreadSignal],
                 initial_capital: float) -> dict:
    """
    Runs all spreads simultaneously.  Returns equity curve and trade list.
    """
    # Build a common date index across all spreads
    all_dates = sorted(
        set.intersection(*[set(ss.spread.index) for ss in signals.values()])
    )
    all_dates = pd.DatetimeIndex(all_dates)

    equity       = float(initial_capital)
    open_pos     = {}          # spread_name → Trade
    all_trades   = []
    eq_curve     = pd.Series(index=all_dates, dtype=float)
    eq_curve.iloc[0] = equity

    spread_names = list(signals.keys())

    for i in range(1, len(all_dates)):
        date     = all_dates[i]
        prev_dt  = all_dates[i - 1]

        # Unrealised mark-to-market (for reporting only, not equity)
        unrealised = 0.0
        for name, trade in open_pos.items():
            ss    = signals[name]
            price = float(ss.spread.loc[date])
            unrealised += (price - trade.entry_price) * trade.direction * \
                          trade.lots * LOT_SIZE

        # ── Manage open positions ──────────────────────────────────────────
        to_close = []
        for name, trade in open_pos.items():
            ss    = signals[name]
            price = float(ss.spread.loc[date])
            sig   = int(ss.signal.loc[date])

            hit_stop   = (
                (trade.direction ==  1 and price <= trade.stop_price) or
                (trade.direction == -1 and price >= trade.stop_price)
            )
            sig_exit   = (sig == 0)
            sig_flip   = (sig != 0 and sig != trade.direction)

            if hit_stop or sig_exit or sig_flip:
                exit_px = trade.stop_price if hit_stop else price
                trade.close(date, exit_px, stopped_out=hit_stop)
                equity += trade.pnl_net
                all_trades.append(trade)
                to_close.append(name)

        for name in to_close:
            del open_pos[name]

        # ── Open new positions ─────────────────────────────────────────────
        for name in spread_names:
            if name in open_pos:
                continue

            ss       = signals[name]
            sig      = int(ss.signal.loc[date])
            prev_sig = int(ss.signal.loc[prev_dt])

            # Only enter on a fresh signal transition
            if sig == 0 or sig == prev_sig:
                continue

            price = float(ss.spread.loc[date])
            atr   = float(ss.atr.loc[date])
            stop  = _stop_price(price, atr, sig)

            notional = target_notional(equity, price, stop)
            if notional <= 0:
                continue

            open_list = list(open_pos.values())
            if not check_capacity(equity, open_list, notional):
                continue

            lots = lots_from_notional(notional, price)
            if lots < 0.01:
                continue

            open_pos[name] = Trade(
                spread_name=name,
                entry_date=date,
                direction=sig,
                notional=notional,
                lots=lots,
                entry_price=price,
                stop_price=stop,
            )

        eq_curve.iloc[i] = equity

    # Close any remaining open positions at last bar
    last_dt = all_dates[-1]
    for name, trade in open_pos.items():
        price = float(signals[name].spread.loc[last_dt])
        trade.close(last_dt, price)
        equity += trade.pnl_net
        all_trades.append(trade)
    if len(open_pos) > 0:
        eq_curve.iloc[-1] = equity

    return {
        "equity":    eq_curve,
        "trades":    all_trades,
        "unrealised": unrealised,
    }
