"""
All tunable parameters live here.
Spread definitions, signal thresholds, risk limits, and execution costs.
"""
from dataclasses import dataclass, field
from typing import List, Tuple

# ── Data ──────────────────────────────────────────────────────────────────────
START_DATE = "2015-01-01"
END_DATE   = "2025-01-01"

# yfinance front-month continuous tickers
TICKERS = {
    "CL": "CL=F",   # WTI crude oil      $/bbl
    "BZ": "BZ=F",   # Brent crude oil    $/bbl
    "HO": "HO=F",   # Heating oil        $/gal  → convert × 42
    "RB": "RB=F",   # RBOB gasoline      $/gal  → convert × 42
}
GALLONS_PER_BARREL = 42.0

# ── Signal ────────────────────────────────────────────────────────────────────
# Parameterised: override per-spread in SPREAD_PARAMS or pass via CLI
DEFAULT_LOOKBACK  = 60      # rolling window for z-score mean/std
DEFAULT_Z_ENTRY   = 1.5     # |z| to open a position
DEFAULT_Z_EXIT    = 0.3     # |z| to close a position
DEFAULT_ATR_MULT  = 2.0     # ATR multiples for hard stop

ATR_PERIOD = 14

# ── Calendar spread approximations ───────────────────────────────────────────
# Disabled by default: EMA-basis on front-month continuous data is not a valid
# proxy for true M1-M2 term structure and loses money consistently in testing.
# Enable only if you have a specific reason; proper calendar spreads require
# expiry-specific contract data (e.g. CLF25 vs CLH25).
INCLUDE_CALENDAR_SPREADS = False

# ── Spread definitions ────────────────────────────────────────────────────────
# legs: list of (ticker_key, multiplier).  All prices converted to $/bbl first.
# divisor: normalises the weighted sum to a per-barrel equivalent.
# category: "crack" | "location" | "product" | "fly" | "condor" | "calendar"

@dataclass
class SpreadDef:
    name:     str
    category: str
    legs:     List[Tuple[str, float]]   # (ticker_key, multiplier)
    divisor:  float = 1.0
    # optional per-spread signal overrides (None → use DEFAULT_*)
    lookback: int   = None
    z_entry:  float = None
    z_exit:   float = None

SPREADS: List[SpreadDef] = [
    # ── Crack spreads ────────────────────────────────────────────────────────
    SpreadDef("crack_321",  "crack",
              [("CL", -3), ("HO", 1), ("RB", 2)], divisor=3,
              lookback=40, z_entry=1.5),

    SpreadDef("crack_211",  "crack",
              [("CL", -2), ("HO", 1), ("RB", 1)], divisor=2,
              lookback=40, z_entry=1.5),

    SpreadDef("crack_ho",   "crack",
              [("CL", -1), ("HO", 1)], divisor=1,
              lookback=30, z_entry=1.5),

    SpreadDef("crack_rb",   "crack",
              [("CL", -1), ("RB", 1)], divisor=1,
              lookback=30, z_entry=1.5),

    # ── Location / quality spreads ───────────────────────────────────────────
    SpreadDef("wti_brent",  "location",
              [("CL", 1), ("BZ", -1)], divisor=1,
              lookback=60, z_entry=1.5),

    # ── Product spread ───────────────────────────────────────────────────────
    SpreadDef("ho_rb",      "product",
              [("HO", 1), ("RB", -1)], divisor=1,
              lookback=30, z_entry=1.5),

    # ── Butterflies (3-leg, buy wings short belly) ───────────────────────────
    # WTI–Brent–HO fly: measures WTI & HO vs Brent
    SpreadDef("fly_wti_bz_ho", "fly",
              [("CL", 1), ("BZ", -2), ("HO", 1)], divisor=2,
              lookback=60, z_entry=1.75),

    # Gasoline–crude–heating fly
    SpreadDef("fly_rb_cl_ho",  "fly",
              [("RB", 1), ("CL", -2), ("HO", 1)], divisor=2,
              lookback=40, z_entry=1.75),

    # ── Condors (4-leg, long outer spreads, short inner) ────────────────────
    # RB–CL spread vs HO–BZ spread
    SpreadDef("condor_rb_cl_ho_bz", "condor",
              [("RB", 1), ("CL", -1), ("BZ", 1), ("HO", -1)], divisor=2,
              lookback=60, z_entry=2.0),

    # ── Outrights (secondary) ────────────────────────────────────────────────
    SpreadDef("outright_cl", "outright",
              [("CL", 1)], divisor=1,
              lookback=20, z_entry=1.5),

    SpreadDef("outright_bz", "outright",
              [("BZ", 1)], divisor=1,
              lookback=20, z_entry=1.5),
]

# ── Risk ──────────────────────────────────────────────────────────────────────
INITIAL_CAPITAL  = 10_000_000   # USD (institutional sizing for futures)
RISK_PER_TRADE   = 0.005        # 0.5% of equity per spread trade
MAX_POSITION_PCT = 0.10         # max 10% notional per single spread
MAX_GROSS_NOTIONAL_PCT = 0.80   # total gross exposure cap vs equity

# ── Execution costs ───────────────────────────────────────────────────────────
COMMISSION_PER_LOT = 3.00       # USD per lot (1 lot = 1,000 bbl) round-trip
SLIPPAGE_PCT       = 0.0002     # 0.02% of notional per side
LOT_SIZE           = 1_000      # barrels per lot (standard crude futures)
