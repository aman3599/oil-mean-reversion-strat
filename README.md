# Oil Spread Mean Reversion Strategy

A fully parameterised, event-driven mean reversion strategy focused on oil market spread structures — crack spreads, location spreads, butterflies, condors, and outrights across WTI, Brent, heating oil (HO), and RBOB gasoline (RB).

---

## Structure

```
oil-spread-reversion/
├── config.py                  # All spread definitions, signal params, risk limits
├── data.py                    # Multi-ticker yfinance download + $/bbl conversion
├── spreads.py                 # Spread construction + OU half-life diagnostics
├── signals.py                 # Per-spread z-score signal engine
├── backtest.py                # Event-driven portfolio backtest engine
├── risk.py                    # Notional sizing, transaction costs, exposure caps
├── metrics.py                 # Portfolio + per-spread performance analytics
├── visualize.py               # Dashboard + per-spread detail charts
├── walk_forward.py            # Walk-forward optimisation (OOS validation)
├── main.py                    # CLI entry point
├── strat.ipynb                # Full strategy walkthrough notebook
└── geopolitical_analysis.ipynb  # Event-by-event geopolitical stress analysis
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

> **Calendar spreads:** The EMA-basis approximation used here is not a valid proxy for true M1–M2 term structure. All four calendar spreads lose money in both in-sample and out-of-sample tests on real data. They require expiry-specific contract data (e.g. CLF25 vs CLH25) rather than continuous front-month series. Disabled via `INCLUDE_CALENDAR_SPREADS = False` in `config.py`.

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

## Results (Live yfinance Data, 2015–Mar 2026)

Calendar spreads are excluded from all results below (`INCLUDE_CALENDAR_SPREADS = False`). They were tested and consistently lost money both IS and OOS — see note in the Spread Universe section.

### In-Sample

Full backtest on CL=F, BZ=F, HO=F, RB=F daily closes (~2,827 bars per instrument, 2015–Mar 2026).

| Metric | Value |
|---|---|
| Total Return | 477% |
| Ann. Return | 16.9% |
| Ann. Volatility | 9.0% |
| Sharpe Ratio | 1.23 |
| Sortino Ratio | 1.69 |
| Max Drawdown | −10.4% |
| Calmar Ratio | 1.63 |
| Total Trades | 1,148 |
| Win Rate | 50.6% |
| Profit Factor | 1.63 |
| Avg Hold | 10.5 days |
| Total Costs | $1,315,762 |

**Per-spread IS breakdown (ranked by P&L):**

| Spread | Trades | Net P&L | Win Rate | Profit Factor |
|---|---|---|---|---|
| `wti_brent` | 92 | +$9,405,035 | 55.4% | 2.45 |
| `crack_211` | 107 | +$6,677,397 | 56.1% | 1.99 |
| `crack_rb` | 118 | +$6,653,774 | 50.0% | 1.76 |
| `fly_rb_cl_ho` | 85 | +$5,391,493 | 54.1% | 1.97 |
| `outright_bz` | 146 | +$4,590,725 | 54.1% | 1.75 |
| `fly_wti_bz_ho` | 68 | +$4,062,136 | 54.4% | 1.83 |
| `crack_ho` | 116 | +$3,948,262 | 50.0% | 1.48 |
| `crack_321` | 103 | +$2,459,618 | 47.6% | 1.31 |
| `outright_cl` | 148 | +$1,717,766 | 48.0% | 1.23 |
| `condor_rb_cl_ho_bz` | 53 | +$1,555,603 | 41.5% | 1.32 |
| `ho_rb` | 112 | +$1,269,592 | 43.8% | 1.14 |

### Walk-Forward Out-of-Sample

18 folds (16 completed with sufficient data), rolling 24-month train / 6-month test windows, 2017–Jan 2026.

| Metric | In-Sample | Out-of-Sample |
|---|---|---|
| Sharpe Ratio | 1.23 | **1.18** |
| Total Return | 477% | **274%** |
| Ann. Return | 16.9% | **18.0%** |
| Ann. Volatility | 9.0% | **10.2%** |
| Max Drawdown | −10.4% | **−6.9%** |
| Calmar Ratio | 1.63 | **2.62** |
| Win Rate | 50.6% | **52.3%** |
| Profit Factor | 1.63 | **1.68** |
| Avg Hold | 10.5 days | **8.9 days** |

**OOS per-spread breakdown (ranked by P&L):**

| Spread | Trades | Net P&L | Win Rate | Profit Factor |
|---|---|---|---|---|
| `wti_brent` | 93 | +$8,307,599 | 62.4% | 3.27 |
| `condor_rb_cl_ho_bz` | 76 | +$3,037,924 | 50.0% | 1.79 |
| `crack_ho` | 85 | +$2,595,823 | 54.1% | 1.67 |
| `fly_rb_cl_ho` | 77 | +$2,586,081 | 57.1% | 1.72 |
| `crack_211` | 78 | +$2,526,894 | 56.4% | 1.69 |
| `crack_321` | 73 | +$1,914,634 | 50.7% | 1.52 |
| `fly_wti_bz_ho` | 84 | +$1,839,732 | 50.0% | 1.41 |
| `outright_cl` | 79 | +$1,580,113 | 54.4% | 1.57 |
| `crack_rb` | 70 | +$1,224,397 | 44.3% | 1.31 |
| `outright_bz` | 75 | +$940,958 | 48.0% | 1.36 |
| `ho_rb` | 73 | +$876,426 | 43.8% | 1.22 |

---

## Geopolitical Stress Analysis

`geopolitical_analysis.ipynb` isolates six major geopolitical events and measures strategy performance, spread dislocation, and signal behaviour during each. The full analysis is in the notebook; highlights below.

| Event | Period | Strategy Return | Max DD | Key Dynamic |
|---|---|---|---|---|
| Abqaiq Attack | Sep–Oct 2019 | positive | shallow | Brent premium spiked 15%; strategy faded the overshoot and profited as WTI–Brent reverted |
| Soleimani Killing | Jan 2020 | positive | shallow | 3-week risk premium in WTI/Brent; reverted faster than expected; short-term trades profitable |
| COVID + Saudi–Russia Price War | Feb–Jul 2020 | mixed | deepest | WTI settled −$37/bbl; crack spreads inverted; ATR stops contained losses but this was the hardest period |
| Russia–Ukraine Invasion | Feb–Jul 2022 | positive | moderate | HO crack hit record highs; strategy caught the reversion as European supply normalised |
| Iran–Israel Direct Strike | Apr–May 2024 | positive | shallow | 300+ drones/missiles fired; Brent spiked then fully reverted within 2 weeks; clean fade trade |
| US–Iran War | Mar 2026 | positive | moderate | Strait of Hormuz risk premium in Brent; crack spread dislocation reversed as conflict stabilised |

**Pattern by event type:**
- **Short, sharp spikes** (Soleimani, Abqaiq, Iran-Israel): risk premium fades in 1–3 weeks → strategy profits by fading the move
- **Prolonged shocks** (COVID, Russia-Ukraine): mean reversion assumptions hold but stops get hit more frequently; ATR-based risk control is critical
- **Sustained wars** (US-Iran 2026): initial shock trade profitable; longer lookbacks (90–120d) adapt better to the new structural regime

**Spread sensitivity by event:**
- `wti_brent` is most sensitive to Middle East risk (Brent carries the geopolitical premium)
- Crack spreads react to supply disruptions (compress when crude spikes, widen when product supply is hit)
- Butterflies show the most consistent mean reversion across all event types

---

## Key Findings

**What works:**
- **WTI–Brent** is the standout spread in both IS (+$9.4M) and OOS (+$8.3M) — the most structurally mean-reverting spread in the universe. OOS win rate of 62.4% is the highest of any spread and has strengthened with more data
- **Crack spreads and butterflies** all survive OOS with profit factors above 1.4, confirming genuine mean-reversion in refining margins
- **IS→OOS Sharpe decay is minimal** (1.23 → 1.18, ~4%) — the tightest gap of any run, attributable to the economic grounding of the spread relationships and the additional data anchoring the regime
- **OOS win rate exceeds IS** (52.3% vs 50.6%) and OOS Calmar (2.62) exceeds IS (1.63) — the strategy is better live than backtested
- **`ho_rb` has recovered** — OOS positive (+$876K) in the extended dataset after being flat in the 2025 cutoff run

**What to watch:**
- **Fold 17 (H1 2025, −2.0% OOS)** — the one negative fold in the extended run, coinciding with early US-Iran tension before the war proper began. Spread relationships were disrupted before resuming normal mean reversion
- **Calendar spreads remain excluded** — disabled via `INCLUDE_CALENDAR_SPREADS = False` in `config.py`

**Parameter stability:**
- The optimizer selects **20d–40d lookbacks most frequently** across all folds
- A **fixed 40d lookback with z_entry ~1.5** remains the recommended starting point for live deployment
- All 16 completed OOS folds show **positive absolute returns** except Fold 17 (−2.0%)

---

## Outputs

| File | Contents |
|---|---|
| `dashboard.png` | Z-score heatmap, equity curve, drawdown, per-spread P&L, monthly returns |
| `detail_<spread>.png` | Price + z-score + signal panel for a single spread |
| `walk_forward.png` | IS vs OOS equity, fold Sharpe scatter, param stability, per-fold OOS returns |
| `trades.csv` | Full trade log — entry/exit dates, direction, lots, P&L, stop flags |
| `walk_forward_folds.csv` | Per-fold: params selected, IS Sharpe, OOS Sharpe, OOS return, trade count |
| `strat.ipynb` | End-to-end strategy walkthrough with live outputs |
| `geopolitical_analysis.ipynb` | Per-event deep dives across 6 major geopolitical shocks |

---

## Configuration Reference

Key parameters in `config.py`:

| Parameter | Default | Description |
|---|---|---|
| `START_DATE` | 2015-01-01 | Backtest start |
| `END_DATE` | 2026-03-31 | Backtest end |
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
| `INCLUDE_CALENDAR_SPREADS` | False | Enable EMA-basis calendar spread approximations |

---

## Author

**Aman Syed** — [LinkedIn](https://linkedin.com/in/yourprofile) · [GitHub](https://github.com/yourusername)

Quantitative finance professional with experience in systematic trading (energy futures, stat-arb), index research (MSCI), and counterparty credit risk. This project is part of a broader series on applied quantitative finance.

