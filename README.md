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

### In-Sample

Full 10-year backtest on CL=F, BZ=F, HO=F, RB=F daily closes (~2,514 bars per instrument).

| Metric | Value |
|---|---|
| Total Return | 215% |
| Ann. Return | 12.2% |
| Ann. Volatility | 9.4% |
| Sharpe Ratio | 0.74 |
| Sortino Ratio | 1.12 |
| Max Drawdown | −12.2% |
| Calmar Ratio | 1.00 |
| Total Trades | 1,183 |
| Win Rate | 45.1% |
| Profit Factor | 1.39 |
| Avg Hold | 9.7 days |
| Total Costs | $1,060,417 |

**Per-spread IS breakdown (ranked by P&L):**

| Spread | Trades | Net P&L | Win Rate | Profit Factor |
|---|---|---|---|---|
| `wti_brent` | 81 | +$5,558,236 | 55.6% | 2.65 |
| `crack_rb` | 102 | +$4,622,039 | 51.0% | 2.01 |
| `crack_211` | 96 | +$4,199,902 | 56.2% | 2.09 |
| `fly_rb_cl_ho` | 75 | +$3,581,081 | 54.7% | 2.17 |
| `crack_ho` | 105 | +$3,059,671 | 51.4% | 1.72 |
| `fly_wti_bz_ho` | 63 | +$3,025,251 | 55.6% | 2.10 |
| `outright_bz` | 131 | +$2,501,954 | 53.4% | 1.68 |
| `crack_321` | 92 | +$2,080,012 | 48.9% | 1.48 |
| `condor_rb_cl_ho_bz` | 47 | +$1,016,401 | 42.6% | 1.39 |
| `outright_cl` | 131 | +$890,933 | 46.6% | 1.20 |
| `ho_rb` | 102 | +$667,807 | 45.1% | 1.13 |
| `cal_*` (4 spreads) | — | **−$9,708,088** | <11% | <0.60 |

### Walk-Forward Out-of-Sample

15 folds (11 completed with sufficient data), rolling 24-month train / 6-month test windows, 2017–2024.

| Metric | In-Sample | Out-of-Sample |
|---|---|---|
| Sharpe Ratio | 0.74 | **0.31** |
| Total Return | 215% | **51%** |
| Ann. Return | 12.2% | **7.9%** |
| Ann. Volatility | 9.4% | **9.7%** |
| Max Drawdown | −12.2% | **−9.4%** |
| Calmar Ratio | 1.00 | **0.83** |
| Win Rate | 45.1% | **41.7%** |
| Profit Factor | 1.39 | **1.26** |
| Avg Hold | 9.7 days | **7.8 days** |

**OOS per-spread breakdown (ranked by P&L):**

| Spread | Trades | Net P&L | Win Rate | Profit Factor |
|---|---|---|---|---|
| `wti_brent` | 49 | +$2,567,327 | 63.3% | 3.33 |
| `fly_wti_bz_ho` | 45 | +$1,473,012 | 55.6% | 2.18 |
| `crack_321` | 43 | +$1,126,611 | 53.5% | 1.89 |
| `fly_rb_cl_ho` | 44 | +$1,016,697 | 54.5% | 1.82 |
| `crack_211` | 45 | +$974,739 | 53.3% | 1.76 |
| `crack_rb` | 42 | +$863,608 | 47.6% | 1.66 |
| `outright_cl` | 43 | +$803,312 | 53.5% | 1.94 |
| `crack_ho` | 47 | +$645,122 | 44.7% | 1.47 |
| `outright_bz` | 41 | +$448,884 | 48.8% | 1.54 |
| `condor_rb_cl_ho_bz` | 39 | +$136,738 | 43.6% | 1.11 |
| `ho_rb` | 39 | −$327,212 | 33.3% | 0.78 |
| `cal_*` (4 spreads) | — | **−$4,579,516** | <14% | <0.44 |

---

## Key Findings

**What works:**
- **WTI–Brent** is the standout spread in both IS and OOS — the location differential is structurally mean-reverting and well-behaved, driven by pipeline dynamics, quality differentials, and storage arbitrage
- **Crack spreads (RB, 211, HO)** and **butterflies** all survive OOS with profit factors above 1.5, confirming genuine mean-reversion in refining margins
- Outrights contribute modestly; useful for diversification but not the core alpha source

**What doesn't work:**
- **Calendar spreads are definitively broken** on continuous front-month data — the EMA-basis approximation produces inverted signals. All four lose money IS and OOS and should be excluded entirely until proper term-structure data is available
- **ho_rb flips negative OOS** (IS profit factor 1.13 → OOS 0.78) — marginal IS edge that doesn't hold, likely noise

**Parameter stability:**
- The in-sample optimizer showed **no stable dominant lookback** on real data (20d–120d selected across folds), unlike the clean 90d preference on synthetic data. This reflects the absence of a single mean-reversion horizon across real oil spreads
- A **fixed 60d lookback with z_entry ~1.75** is recommended over per-fold optimisation for live deployment — more robust, less overfit
- The IS→OOS Sharpe decay (~60%) is consistent with commodity mean reversion strategies in the literature

**Worst periods:**
- **2018 H1** (Fold 3, −4.8% OOS): WTI–Brent spread blew out structurally on US shale supply surges
- **2024 H1** (Fold 15, −4.2% OOS): Worst single fold — spread relationships shifted amid OPEC+ production changes; worth monitoring going forward

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
