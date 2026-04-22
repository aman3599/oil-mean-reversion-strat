"""
Walk-forward optimisation engine.

Each fold:
  1. Train window  → grid-search (lookback × z_entry) → best Sharpe params
  2. Test window   → run backtest with those params (out-of-sample)
  3. Advance both windows by test_months; repeat.

Final output: stitched OOS equity curve + fold summary table.
"""
import warnings
import itertools
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

warnings.filterwarnings("ignore")

from config   import INITIAL_CAPITAL, DEFAULT_Z_EXIT
from spreads  import build_all_spreads
from signals  import compute_signals
from backtest import run_backtest
from metrics  import portfolio_stats, per_spread_stats, _dd_series, sharpe_float

# ── Search space ──────────────────────────────────────────────────────────────
LOOKBACKS = [20, 40, 60, 90, 120]
Z_ENTRIES = [1.0, 1.25, 1.5, 1.75, 2.0]

DARK   = "#0d1117";  PANEL  = "#161b22";  GRID   = "#21262d"
TEXT   = "#c9d1d9";  GREEN  = "#3fb950";  RED    = "#f85149"
BLUE   = "#58a6ff";  GOLD   = "#d29922";  PURPLE = "#bc8cff"


def _slice_prices(prices: dict, start, end) -> dict:
    return {k: v.loc[start:end] for k, v in prices.items()}


def _run_fold(prices_slice: dict, lookback: int, z_entry: float,
              z_exit: float, capital: float) -> dict:
    spreads = build_all_spreads(prices_slice)
    if spreads.empty or len(spreads) < lookback + 10:
        return None
    sigs   = compute_signals(spreads,
                             lookback_override=lookback,
                             z_entry_override=z_entry,
                             z_exit_override=z_exit)
    return run_backtest(sigs, capital)


def _best_params(prices_slice: dict, z_exit: float) -> tuple[int, float, float]:
    """Grid search on train slice. Returns (lookback, z_entry, best_sharpe)."""
    best_sharpe = -np.inf
    best_lb, best_ze = LOOKBACKS[-1], Z_ENTRIES[2]

    for lb, ze in itertools.product(LOOKBACKS, Z_ENTRIES):
        res = _run_fold(prices_slice, lb, ze, z_exit, INITIAL_CAPITAL)
        if res is None or len(res["trades"]) < 5:
            continue
        sh = sharpe_float(res["equity"])
        if np.isnan(sh):
            continue
        if sh > best_sharpe:
            best_sharpe, best_lb, best_ze = sh, lb, ze

    return best_lb, best_ze, best_sharpe


def run_walk_forward(prices: dict,
                     train_months: int = 24,
                     test_months:  int = 6,
                     z_exit: float = DEFAULT_Z_EXIT) -> dict:
    """
    Roll train/test windows across the full price history.
    Returns OOS equity, fold summary, and all OOS trades.
    """
    all_dates = sorted(
        set.intersection(*[set(v.index) for v in prices.values()])
    )
    start_dt = pd.Timestamp(all_dates[0])
    end_dt   = pd.Timestamp(all_dates[-1])

    folds     = []
    oos_eq    = []          # list of equity Series, one per fold
    oos_trades= []
    equity    = float(INITIAL_CAPITAL)   # capital rolls forward fold-to-fold

    fold_num  = 0
    train_start = start_dt

    while True:
        train_end = train_start + pd.DateOffset(months=train_months)
        test_start= train_end  + pd.Timedelta(days=1)
        test_end  = test_start + pd.DateOffset(months=test_months)

        if test_end > end_dt:
            break

        print(f"  Fold {fold_num+1:>2}  "
              f"train [{train_start.date()} → {train_end.date()}]  "
              f"test  [{test_start.date()} → {test_end.date()}]", end="  ")

        # ── Optimise on train ──────────────────────────────────────────────
        train_px = _slice_prices(prices, train_start, train_end)
        lb, ze, is_sharpe = _best_params(train_px, z_exit)

        # ── Trade on test (OOS) ───────────────────────────────────────────
        test_px  = _slice_prices(prices, test_start, test_end)
        res = _run_fold(test_px, lb, ze, z_exit, equity)

        if res is None or res["equity"].empty:
            print(f"lb={lb} ze={ze}  IS={is_sharpe:.2f}  OOS=skip (no data)")
            train_start += pd.DateOffset(months=test_months)
            fold_num += 1
            continue

        oos_eq_fold = res["equity"]
        trades_fold = res["trades"]

        # Scale equity: fold starts where prior fold ended
        scale = equity / oos_eq_fold.iloc[0]
        oos_eq_fold = oos_eq_fold * scale

        end_equity = float(oos_eq_fold.iloc[-1])
        fold_ret   = end_equity / equity - 1

        oos_sh = sharpe_float(oos_eq_fold)

        print(f"lb={lb:>3} ze={ze:.2f}  "
              f"IS={is_sharpe:>5.2f}  "
              f"OOS={oos_sh:>5.2f}  "
              f"OOS ret={fold_ret:>+.1%}  "
              f"trades={len(trades_fold)}")

        folds.append({
            "fold":        fold_num + 1,
            "train_start": train_start.date(),
            "train_end":   train_end.date(),
            "test_start":  test_start.date(),
            "test_end":    test_end.date(),
            "best_lb":     lb,
            "best_ze":     ze,
            "is_sharpe":   round(is_sharpe, 3),
            "oos_sharpe":  round(oos_sh, 3),
            "oos_return":  round(fold_ret, 4),
            "n_trades":    len(trades_fold),
        })

        oos_eq.append(oos_eq_fold)
        oos_trades.extend(trades_fold)
        equity = end_equity

        train_start += pd.DateOffset(months=test_months)
        fold_num += 1

    if not oos_eq:
        raise ValueError("No OOS folds completed — check date range vs train/test sizes.")

    # Stitch OOS equity (each fold already scaled to continue from prior)
    combined_eq = pd.concat(oos_eq).sort_index()
    combined_eq = combined_eq[~combined_eq.index.duplicated(keep="last")]

    fold_df = pd.DataFrame(folds)
    return {
        "equity":       combined_eq,
        "trades":       oos_trades,
        "folds":        fold_df,
        "initial_cap":  INITIAL_CAPITAL,
    }


def plot_walk_forward(wf: dict, is_equity: pd.Series,
                      save_path: str = "walk_forward.png"):
    oos_eq  = wf["equity"]
    folds   = wf["folds"]
    trades  = wf["trades"]
    init    = wf["initial_cap"]

    fig = plt.figure(figsize=(18, 20), facecolor=DARK)
    gs  = gridspec.GridSpec(4, 2, figure=fig, hspace=0.5, wspace=0.3,
                             top=0.93, bottom=0.05, left=0.07, right=0.96)

    fig.text(0.5, 0.962, "Walk-Forward Analysis — Oil Spread Mean Reversion",
             ha="center", color=TEXT, fontsize=14, fontweight="bold")
    fig.text(0.5, 0.948,
             f"{len(folds)} folds · "
             f"{folds['best_lb'].mode()[0]}d lookback (modal best) · "
             f"OOS period: {oos_eq.index[0].date()} → {oos_eq.index[-1].date()}",
             ha="center", color=GOLD, fontsize=8.5)

    def _style(ax, title=""):
        ax.set_facecolor(PANEL)
        ax.tick_params(colors=TEXT, labelsize=7)
        for sp in ax.spines.values():
            sp.set_color(GRID)
        ax.xaxis.label.set_color(TEXT)
        ax.yaxis.label.set_color(TEXT)
        if title:
            ax.set_title(title, color=TEXT, fontsize=9, pad=5, fontweight="bold")
        ax.grid(True, color=GRID, lw=0.4, alpha=0.7)

    # ── 1. IS vs OOS equity overlay ───────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    # Align IS equity to same start as OOS for comparison
    is_trim = is_equity.loc[oos_eq.index[0]:]
    is_scale = (init / is_trim.iloc[0]) if not is_trim.empty else 1.0
    ax1.plot(is_trim.index, is_trim * is_scale / 1e6,
             color=BLUE, lw=0.9, alpha=0.6, ls="--", label="In-sample (IS)")
    ax1.plot(oos_eq.index, oos_eq / 1e6,
             color=GREEN, lw=1.3, label="Out-of-sample (OOS)")
    ax1.axhline(init / 1e6, color=TEXT, ls=":", lw=0.5, alpha=0.5)

    # Shade each fold alternately
    for _, row in folds.iterrows():
        alpha = 0.04 if row["fold"] % 2 == 0 else 0.08
        ax1.axvspan(pd.Timestamp(row["test_start"]),
                    pd.Timestamp(row["test_end"]),
                    color=GOLD, alpha=alpha)

    ax1.set_ylabel("Equity ($M)", color=TEXT)
    ax1.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT)
    _style(ax1, "IS vs OOS Equity Curve (OOS folds shaded)")

    # ── 2. OOS drawdown ───────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    dd = _dd_series(oos_eq) * 100
    ax2.fill_between(dd.index, dd, 0, color=RED, alpha=0.45)
    ax2.plot(dd.index, dd, color=RED, lw=0.6)
    ax2.set_ylabel("Drawdown (%)")
    _style(ax2, "OOS Drawdown")

    # ── 3. Fold IS vs OOS Sharpe scatter ─────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.scatter(folds["is_sharpe"], folds["oos_sharpe"],
                color=GOLD, s=60, zorder=3, alpha=0.85)
    for _, row in folds.iterrows():
        ax3.annotate(f"F{int(row['fold'])}", (row["is_sharpe"], row["oos_sharpe"]),
                     fontsize=6, color=TEXT, textcoords="offset points", xytext=(4, 3))
    mn = min(folds["is_sharpe"].min(), folds["oos_sharpe"].min()) - 0.2
    mx = max(folds["is_sharpe"].max(), folds["oos_sharpe"].max()) + 0.2
    ax3.plot([mn, mx], [mn, mx], color=TEXT, lw=0.6, ls="--", alpha=0.4)
    ax3.axhline(0, color=RED, lw=0.5, ls="--", alpha=0.6)
    ax3.set_xlabel("IS Sharpe")
    ax3.set_ylabel("OOS Sharpe")
    _style(ax3, "IS vs OOS Sharpe per Fold")

    # ── 4. Best params per fold ───────────────────────────────────────────
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.bar(folds["fold"], folds["best_lb"], color=BLUE, alpha=0.8, label="Lookback")
    ax4.set_xticks(folds["fold"])
    ax4.set_xlabel("Fold")
    ax4.set_ylabel("Best Lookback (days)")
    _style(ax4, "Selected Lookback per Fold")

    ax5 = fig.add_subplot(gs[2, 1])
    ax5.bar(folds["fold"], folds["best_ze"], color=PURPLE, alpha=0.8)
    ax5.set_xticks(folds["fold"])
    ax5.set_xlabel("Fold")
    ax5.set_ylabel("Best Z-Entry")
    _style(ax5, "Selected Z-Entry Threshold per Fold")

    # ── 5. OOS return per fold ────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[3, :])
    colors = [GREEN if r > 0 else RED for r in folds["oos_return"]]
    ax6.bar(folds["fold"], folds["oos_return"] * 100, color=colors, alpha=0.85)
    ax6.axhline(0, color=TEXT, lw=0.6)
    ax6.set_xticks(folds["fold"])
    ax6.set_xticklabels([f"F{int(f)}\n{str(row.test_start)[:7]}"
                         for f, (_, row) in zip(folds["fold"], folds.iterrows())],
                        fontsize=7)
    ax6.set_ylabel("OOS Return (%)")
    _style(ax6, "OOS Return per Fold (%)")

    plt.savefig(save_path, dpi=150, bbox_inches="tight",
                facecolor=DARK, edgecolor="none")
    plt.close()
    print(f"Walk-forward chart → {save_path}")


def print_fold_summary(wf: dict):
    folds = wf["folds"]
    print("\n" + "=" * 82)
    print(f"  WALK-FORWARD SUMMARY  ({len(folds)} folds)")
    print("=" * 82)
    print(f"  {'Fold':>4}  {'Train':^22}  {'Test':^22}  "
          f"{'lb':>4} {'ze':>5}  {'IS Sh':>6}  {'OOS Sh':>6}  {'OOS Ret':>8}  {'#Tr':>4}")
    print("  " + "-" * 78)
    for _, r in folds.iterrows():
        print(f"  {int(r.fold):>4}  "
              f"{str(r.train_start)} → {str(r.train_end)}  "
              f"{str(r.test_start)} → {str(r.test_end)}  "
              f"{int(r.best_lb):>4} {r.best_ze:>5.2f}  "
              f"{r.is_sharpe:>6.2f}  {r.oos_sharpe:>6.2f}  "
              f"{r.oos_return:>+7.1%}  {int(r.n_trades):>4}")
    print("=" * 82)

    oos_eq  = wf["equity"]
    trades  = wf["trades"]
    stats   = portfolio_stats(oos_eq, trades)
    per_sp  = per_spread_stats(trades)

    print("\nOOS Portfolio Stats:")
    for k, v in stats.items():
        print(f"  {k:<24} {v}")

    print("\nOOS Per-Spread Breakdown:")
    print(per_sp.to_string(index=False))
