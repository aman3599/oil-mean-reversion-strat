"""
Position sizing and transaction cost modelling for spread trades.

All sizing is done in notional-dollar terms; lot counts are computed
afterwards for reporting (1 lot = 1,000 barrels).
"""
import numpy as np
from config import (RISK_PER_TRADE, MAX_POSITION_PCT, MAX_GROSS_NOTIONAL_PCT,
                    COMMISSION_PER_LOT, SLIPPAGE_PCT, LOT_SIZE)


def target_notional(equity: float, entry_spread: float, stop_spread: float,
                    risk_per_trade: float = RISK_PER_TRADE,
                    max_pct: float = MAX_POSITION_PCT) -> float:
    """
    Dollar notional to deploy on this spread trade.
    Sizes so that a stop-out costs at most risk_per_trade × equity.
    Denominated in $/barrel × 1 bbl (spread is already in $/bbl units).
    """
    stop_dist = abs(entry_spread - stop_spread)      # $/bbl
    if stop_dist < 0.01:                              # guard near-zero stop
        stop_dist = max(0.01, abs(entry_spread) * 0.05)

    risk_dollars = equity * risk_per_trade
    lots = risk_dollars / (stop_dist * LOT_SIZE)     # risk-based lots
    max_lots = (equity * max_pct) / (max(abs(entry_spread), 1.0) * LOT_SIZE)
    lots = min(lots, max_lots)
    return max(0.0, lots * abs(entry_spread) * LOT_SIZE)


def lots_from_notional(notional: float, entry_spread: float) -> float:
    denom = abs(entry_spread) * LOT_SIZE
    return notional / denom if denom > 0 else 0.0


def transaction_cost(notional: float, lots: float) -> float:
    """Round-trip cost: commissions + slippage on both legs."""
    commission = lots * COMMISSION_PER_LOT
    slip       = 2 * SLIPPAGE_PCT * notional
    return commission + slip


def gross_notional(open_positions: list) -> float:
    return sum(abs(p.notional) for p in open_positions)


def check_capacity(equity: float, open_positions: list, new_notional: float) -> bool:
    return (gross_notional(open_positions) + new_notional) <= equity * MAX_GROSS_NOTIONAL_PCT
