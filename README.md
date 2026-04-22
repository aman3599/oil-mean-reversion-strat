# Oil Spread Mean Reversion Strategy

A fully parameterised, event-driven mean reversion strategy focused on oil market spread structures — crack spreads, location spreads, butterflies, condors, and outrights across WTI, Brent, heating oil (HO), and RBOB gasoline (RB).

---

## Structure

```
oil-spread-reversion/
├── config.py          # All spread definitions, signal params, risk limits
├── data.py            # Multi-ticker yfinance download + $/bbl conversion
├── spreads.py         # Spread construction + OU half-life diagnostics
├── signals.py         # Per-spread z-score signal engine
├── backtest.py        # Event-driven portfolio backtest engine
├── risk.py            # Notional sizing, transaction costs, exposure caps
├── metrics.py         # Portfolio + per-spread performance analytics
├── visualize.py       # Dashboard + per-spread detail charts
├── walk_forward.py    # Walk-forward optimisation (OOS validation)
└── main.py            # CLI entry point
```

---

## Spread Universe

| Spread | Category | Legs |
|---|---|---|
| `crack_321` | Crack | −3 CL + 1 HO + 2 RB |
| `crack_211` | Crack | −2 CL + 1 HO + 1 RB |
| `crack_ho` | Crack | −1 CL + 1 HO |
| `crack_rb` | Crack | −1 CL + 1 RB |
| `wti_brent` | Location | CL − BZ |
| `ho_rb` | Product | HO − RB |
| `fly_wti_bz_ho` | Butterfly | CL − 2·BZ + HO |
| `fly_rb_cl_ho` | Butterfly | RB − 2·CL + HO |
| `condor_rb_cl_ho_bz` | Condor | (RB−CL) − (HO−BZ) |
| `outright_cl` | Outright | CL |
| `outright_bz` | Outright | BZ |
| `cal_*` | Calendar | ⚠️ Excluded — see note below |

All HO and RB prices are converted from $/gallon → $/barrel (×42) before spread construction so every spread is expressed in comparable $/bbl units.

> **Calendar spreads:** The EMA-basis approximation used here is not a valid proxy for true M1–M2 term structure. All four calendar spreads lose money in both in-sample and out-of-sample tests on real data. They require expiry-specific contract data (e.g. CLF25 vs CLH25) rather than continuous front-month series. Remove them from `SPREADS` in `config.py` for any live use.

---

## Signal Logic

Each spread uses a **rolling z-score**:

```
z(t) = (spread(t) − μ(t, w)) / σ(t, w)
```

- **Entry long spread**: z < −z_entry → spread is abnormally cheap, expect reversion up
- **Entry short spread**: z > +z_entry → spread is abnormally expensive, expect reversion down
- **Exit**: |z| < z_exit (mean reversion realised)
- **Hard stop**: ATR-based stop (`DEFAULT_ATR_MULT × ATR14` from entry price)

Parameters are set globally in `config.py`, can be overridden per spread inside `SPREADS`, and can be passed at runtime via CLI flags.

---

## Risk Model

- **Sizing**: `risk_per_trade × equity / (stop_distance_$/bbl × lot_size)`
- **Cap**: max 10% of equity notional per spread; max 80% gross across portfolio
- **Costs**: `COMMISSION_PER_LOT` ($3 per round-trip lot) + `SLIPPAGE_PCT` (0.02% per side)
- All sizing in notional-dollar terms; lot counts are reported as reference only

---

## Usage

```bash
# Standard backtest with config defaults
python main.py

# Override signal parameters globally
python main.py --lookback 60 --z-entry 1.75

# Grid search over lookback × z_entry (in-sample only)
python main.py --optimize

# Walk-forward OOS validation (24m train, 6m test windows)
python main.py --walk-forward

# Adjust walk-forward window sizes
python main.py --walk-forward --train-months 36 --test-months 3

# Print spread descriptive stats + OU half-lives
python main.py --stats

# Detailed chart for a single spread
python main.py --detail wti_brent
```

---

## Results (Live yfinance Data, 2015–2025)

Calendar spreads are excluded from all results below (`INCLUDE_CALENDAR_SPREADS = False`). They were tested and consistently lost money both IS and OOS due to the EMA-basis approximation being an invalid proxy for real term structure — see note in the Spread Universe section.

### In-Sample

Full 10-year backtest on CL=F, BZ=F, HO=F, RB=F daily closes (~2,514 bars per instrument).

| Metric | Value |
|---|---|
| Total Return | 436% |
| Ann. Return | 18.3% |
| Ann. Volatility | 9.1% |
| Sharpe Ratio | 1.34 |
| Sortino Ratio | 1.83 |
| Max Drawdown | −10.4% |
| Calmar Ratio | 1.76 |
| Total Trades | 1,025 |
| Win Rate | 51.0% |
| Profit Factor | 1.73 |
| Avg Hold | 10.4 days |
| Total Costs | $1,040,757 |

**Per-spread IS breakdown (ranked by P&L):**

| Spread | Trades | Net P&L | Win Rate | Profit Factor |
|---|---|---|---|---|
| `wti_brent` | 81 | +$8,207,660 | 55.6% | 2.72 |
| `crack_rb` | 102 | +$6,336,579 | 51.0% | 1.98 |
| `crack_211` | 96 | +$5,806,200 | 56.2% | 2.06 |
| `fly_rb_cl_ho` | 75 | +$4,709,001 | 54.7% | 2.09 |
| `crack_ho` | 105 | +$4,631,223 | 51.4% | 1.77 |
| `fly_wti_bz_ho` | 63 | +$3,937,247 | 55.6% | 2.00 |
| `outright_bz` | 131 | +$3,725,545 | 53.4% | 1.73 |
| `crack_321` | 92 | +$2,593,861 | 48.9% | 1.42 |
| `outright_cl` | 131 | +$1,457,681 | 46.6% | 1.23 |
| `condor_rb_cl_ho_bz` | 47 | +$1,284,130 | 42.6% | 1.34 |
| `ho_rb` | 102 | +$933,081 | 45.1% | 1.13 |

### Walk-Forward Out-of-Sample

15 folds (13 completed with sufficient data), rolling 24-month train / 6-month test windows, 2017–2024.

| Metric | In-Sample | Out-of-Sample |
|---|---|---|
| Sharpe Ratio | 1.34 | **1.12** |
| Total Return | 436% | **186%** |
| Ann. Return | 18.3% | **17.6%** |
| Ann. Volatility | 9.1% | **10.5%** |
| Max Drawdown | −10.4% | **−6.9%** |
| Calmar Ratio | 1.76 | **2.56** |
| Win Rate | 51.0% | **51.0%** |
| Profit Factor | 1.73 | **1.66** |
| Avg Hold | 10.4 days | **8.7 days** |

**OOS per-spread breakdown (ranked by P&L):**

| Spread | Trades | Net P&L | Win Rate | Profit Factor |
|---|---|---|---|---|
| `wti_brent` | 69 | +$4,625,418 | 60.9% | 2.83 |
| `fly_rb_cl_ho` | 60 | +$2,607,402 | 58.3% | 2.09 |
| `crack_211` | 61 | +$2,548,214 | 57.4% | 2.04 |
| `crack_321` | 58 | +$1,930,588 | 53.4% | 1.77 |
| `crack_ho` | 63 | +$1,621,200 | 49.2% | 1.59 |
| `crack_rb` | 52 | +$1,480,559 | 42.3% | 1.59 |
| `condor_rb_cl_ho_bz` | 58 | +$1,195,972 | 46.6% | 1.40 |
| `outright_cl` | 57 | +$1,073,733 | 52.6% | 1.56 |
| `fly_wti_bz_ho` | 63 | +$917,554 | 49.2% | 1.30 |
| `outright_bz` | 57 | +$634,867 | 47.4% | 1.35 |
| `ho_rb` | 57 | −$50,743 | 40.4% | 0.98 |

---

## Key Findings

**What works:**
- **WTI–Brent** is the standout spread in both IS (+$8.2M) and OOS (+$4.6M) — the most structurally mean-reverting spread in the universe, anchored by pipeline dynamics, quality differentials, and storage arbitrage. OOS win rate of 60.9% is the highest of any spread
- **Crack spreads (RB, 211, HO)** and **butterflies** all survive OOS with profit factors above 1.5, confirming genuine mean-reversion in refining margins
- **IS→OOS Sharpe decay is minimal** (1.34 → 1.12, ~16%) — unusually low for a commodity strategy, attributable to the economic grounding of these spread relationships
- OOS **win rate matches IS exactly** (51.0%) — a strong signal the strategy isn't curve-fit
- Outrights contribute modestly; useful for diversification but not the core alpha source

**What to watch:**
- **`ho_rb` is marginal** — IS profit factor 1.13, OOS essentially flat (−$50K, PF 0.98). The heating oil vs gasoline seasonal relationship has weakened as US refinery exports grew. Consider removing if it continues to underperform
- **Calendar spreads were tested and removed** — the EMA-basis approximation on front-month continuous data is invalid. Disabled via `INCLUDE_CALENDAR_SPREADS = False` in `config.py`

**Parameter stability:**
- The optimizer selects **20d–60d lookbacks most frequently** on real data — shorter than the 90d that dominated on synthetic OU data. Real oil spreads have faster mean-reversion dynamics than the synthetic process assumed
- A **fixed 40d lookback with z_entry ~1.5** is a reasonable starting point for live deployment — balances responsiveness with noise reduction
- All 13 completed OOS folds are **positive in absolute return**, with only Fold 15 (2024 H1) showing a negative Sharpe (−0.25) despite a +1.4% return — low activity rather than a losing period

**Worst period:**
- **2024 H1** (Fold 15): Lowest OOS Sharpe (−0.25) amid OPEC+ production uncertainty compressing spread volatility. Worth monitoring as a potential regime shift

---

## Outputs

| File | Contents |
|---|---|
| `dashboard.png` | Z-score heatmap, equity curve, drawdown, per-spread P&L, monthly returns |
| `detail_<spread>.png` | Price + z-score + signal panel for a single spread |
| `walk_forward.png` | IS vs OOS equity, fold Sharpe scatter, param stability, per-fold OOS returns |
| `trades.csv` | Full trade log — entry/exit dates, direction, lots, P&L, stop flags |
| `walk_forward_folds.csv` | Per-fold: params selected, IS Sharpe, OOS Sharpe, OOS return, trade count |

---

## Configuration Reference

Key parameters in `config.py`:

| Parameter | Default | Description |
|---|---|---|
| `DEFAULT_LOOKBACK` | 60 | Z-score rolling window (days) |
| `DEFAULT_Z_ENTRY` | 1.5 | \|z\| threshold to open a position |
| `DEFAULT_Z_EXIT` | 0.3 | \|z\| threshold to close a position |
| `DEFAULT_ATR_MULT` | 2.0 | ATR multiples for hard stop |
| `ATR_PERIOD` | 14 | ATR calculation period |
| `RISK_PER_TRADE` | 0.005 | Fraction of equity risked per trade (0.5%) |
| `MAX_POSITION_PCT` | 0.10 | Max notional per spread vs equity (10%) |
| `MAX_GROSS_NOTIONAL_PCT` | 0.80 | Portfolio gross exposure cap (80%) |
| `INITIAL_CAPITAL` | $10,000,000 | Starting equity |
| `COMMISSION_PER_LOT` | $3.00 | Round-trip commission per lot |
| `SLIPPAGE_PCT` | 0.0002 | Slippage per side (0.02% of notional) |
