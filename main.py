"""
Oil Spread Mean Reversion — CLI Runner

Usage:
    python main.py                             # run with config defaults
    python main.py --lookback 40 --z-entry 1.5
    python main.py --optimize                  # grid search over parameters
    python main.py --stats                     # print spread stats / half-lives
    python main.py --detail crack_321          # detailed chart for one spread
"""
import argparse
import warnings
import itertools
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from config       import (START_DATE, END_DATE, INITIAL_CAPITAL, SPREADS,
                          DEFAULT_LOOKBACK, DEFAULT_Z_ENTRY, DEFAULT_Z_EXIT)
from data         import fetch_all
from spreads      import build_all_spreads, spread_descriptive_stats
from signals      import compute_signals
from backtest     import run_backtest
from metrics      import portfolio_stats, per_spread_stats, sharpe_float
from visualize    import plot_dashboard, plot_spread_detail
from walk_forward import run_walk_forward, plot_walk_forward, print_fold_summary


# ── Core runner ───────────────────────────────────────────────────────────────
def run(prices, lookback=None, z_entry=None, z_exit=None, verbose=True):
    spreads_df = build_all_spreads(prices)
    sigs       = compute_signals(spreads_df,
                                 lookback_override=lookback,
                                 z_entry_override=z_entry,
                                 z_exit_override=z_exit)
    result     = run_backtest(sigs, INITIAL_CAPITAL)
    stats      = portfolio_stats(result["equity"], result["trades"])
    per_sp     = per_spread_stats(result["trades"])

    if verbose:
        print("\n" + "=" * 56)
        print("  OIL SPREAD MEAN REVERSION — PORTFOLIO SUMMARY")
        print("=" * 56)
        for k, v in stats.items():
            print(f"  {k:<24} {v}")
        print("=" * 56)
        print("\nPer-Spread Breakdown:")
        print(per_sp.to_string(index=False))

    return result, stats, per_sp, spreads_df, sigs


# ── Parameter sweep ───────────────────────────────────────────────────────────
def optimize(prices):
    lookbacks = [20, 40, 60, 90, 120]
    z_entries = [1.0, 1.25, 1.5, 1.75, 2.0]
    print(f"\nOptimisation grid: {len(lookbacks)} lookbacks × {len(z_entries)} z_entry levels\n")

    best = {"sharpe": -np.inf, "lookback": None, "z_entry": None}
    rows = []
    for lb, ze in itertools.product(lookbacks, z_entries):
        result, stats, *_ = run(prices, lookback=lb, z_entry=ze,
                                 z_exit=DEFAULT_Z_EXIT, verbose=False)
        sh = sharpe_float(result["equity"])
        rows.append({"lookback": lb, "z_entry": ze, "sharpe": round(sh, 3),
                     "tot_ret": stats["Total Return"],
                     "max_dd": stats["Max Drawdown"],
                     "n_trades": stats["Total Trades"]})
        if sh > best["sharpe"]:
            best = {"sharpe": sh, "lookback": lb, "z_entry": ze}

    grid_df = pd.DataFrame(rows)
    pivot   = grid_df.pivot(index="lookback", columns="z_entry", values="sharpe")
    print("Sharpe Ratio grid:")
    print(pivot.to_string())
    print(f"\nBest: lookback={best['lookback']}, z_entry={best['z_entry']}, "
          f"Sharpe={best['sharpe']:.3f}\n")
    return best["lookback"], best["z_entry"]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback",  type=int,   default=None)
    parser.add_argument("--z-entry",   type=float, default=None)
    parser.add_argument("--z-exit",    type=float, default=None)
    parser.add_argument("--optimize",  action="store_true")
    parser.add_argument("--stats",     action="store_true",
                        help="Print spread descriptive stats and half-lives")
    parser.add_argument("--detail",    type=str, default=None,
                        help="Generate detailed chart for a named spread")
    parser.add_argument("--rf",           type=float, default=0.05,
                        help="Risk-free rate for Sharpe (default 0.05)")
    parser.add_argument("--walk-forward", action="store_true",
                        help="Run walk-forward optimisation (OOS test)")
    parser.add_argument("--train-months", type=int, default=24,
                        help="Training window in months (default 24)")
    parser.add_argument("--test-months",  type=int, default=6,
                        help="Test window in months (default 6)")
    args = parser.parse_args()

    print(f"\nFetching prices: {START_DATE} → {END_DATE}")
    prices = fetch_all(START_DATE, END_DATE)

    if args.stats:
        spreads_df = build_all_spreads(prices)
        print("\nSpread Descriptive Stats:")
        print(spread_descriptive_stats(spreads_df).to_string())
        return

    lookback = args.lookback
    z_entry  = args.z_entry
    z_exit   = args.z_exit

    if args.optimize:
        lookback, z_entry = optimize(prices)

    result, stats, per_sp, spreads_df, sigs = run(
        prices, lookback=lookback, z_entry=z_entry, z_exit=z_exit
    )

    # Save trade log
    trades = result["trades"]
    if trades:
        log = pd.DataFrame([{
            "spread":      t.spread_name,
            "entry":       t.entry_date.date(),
            "exit":        t.exit_date.date() if t.exit_date else None,
            "direction":   "Long" if t.direction == 1 else "Short",
            "lots":        round(t.lots, 2),
            "entry_px":    round(t.entry_price, 4),
            "exit_px":     round(t.exit_price, 4) if t.exit_price else None,
            "pnl_net":     round(t.pnl_net, 0),
            "hold_days":   t.hold_days,
            "stopped_out": t.stopped_out,
        } for t in trades])
        log.to_csv("trades.csv", index=False)
        print(f"\nTrade log → trades.csv  ({len(log)} trades)")

    # ── Walk-forward ───────────────────────────────────────────────────────
    if args.walk_forward:
        print(f"\nRunning walk-forward  "
              f"(train={args.train_months}m, test={args.test_months}m)...")
        wf = run_walk_forward(prices,
                              train_months=args.train_months,
                              test_months=args.test_months,
                              z_exit=z_exit or DEFAULT_Z_EXIT)
        print_fold_summary(wf)
        plot_walk_forward(wf, result["equity"], save_path="walk_forward.png")
        wf["folds"].to_csv("walk_forward_folds.csv", index=False)
        print("Fold table → walk_forward_folds.csv")

    # Main dashboard
    plot_dashboard(sigs, result["equity"], result["trades"],
                   per_sp, stats, spreads_df,
                   save_path="dashboard.png")

    # Detail chart for one spread
    detail_name = args.detail or per_sp["spread"].iloc[0]
    if detail_name in sigs:
        sp_trades = [t for t in trades if t.spread_name == detail_name]
        plot_spread_detail(sigs[detail_name], sp_trades,
                           save_path=f"detail_{detail_name}.png")
        print(f"Detail chart → detail_{detail_name}.png")


if __name__ == "__main__":
    main()
