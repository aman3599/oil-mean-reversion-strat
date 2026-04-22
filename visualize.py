"""
Multi-panel dashboard covering:
  1.  Z-score heatmap across all spreads
  2.  Individual spread price + z-score for selected spreads
  3.  Portfolio equity curve + drawdown
  4.  Per-spread P&L bar chart
  5.  Trade PnL distribution
  6.  Monthly returns heatmap
"""
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
from matplotlib.patches import FancyBboxPatch

from signals import SpreadSignal, zscore_heatmap_data
from metrics import _dd_series, monthly_returns

warnings.filterwarnings("ignore")

# ── Theme ─────────────────────────────────────────────────────────────────────
DARK   = "#0d1117"
PANEL  = "#161b22"
GRID   = "#21262d"
TEXT   = "#c9d1d9"
GREEN  = "#3fb950"
RED    = "#f85149"
BLUE   = "#58a6ff"
GOLD   = "#d29922"
PURPLE = "#bc8cff"

CAT_COLORS = {
    "crack":    GOLD,
    "location": BLUE,
    "product":  PURPLE,
    "fly":      GREEN,
    "condor":   "#ff7b72",
    "calendar": "#39d353",
    "outright": TEXT,
}


def _style(ax, title=""):
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=TEXT, labelsize=7)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    if title:
        ax.set_title(title, color=TEXT, fontsize=9, pad=5, fontweight="bold")
    ax.grid(True, color=GRID, lw=0.4, alpha=0.8)


def plot_dashboard(signals: dict[str, SpreadSignal],
                   equity: pd.Series,
                   trades: list,
                   per_spread: pd.DataFrame,
                   stats: dict,
                   spreads_df: pd.DataFrame,
                   save_path: str = "dashboard.png"):

    fig = plt.figure(figsize=(22, 28), facecolor=DARK)
    gs  = gridspec.GridSpec(
        6, 3, figure=fig,
        hspace=0.55, wspace=0.35,
        top=0.93, bottom=0.04, left=0.06, right=0.97,
    )

    # ── Title ─────────────────────────────────────────────────────────────────
    fig.text(0.5, 0.965, "Oil Spread Mean Reversion Strategy",
             ha="center", color=TEXT, fontsize=16, fontweight="bold")
    fig.text(0.5, 0.952, "Crack Spreads · Calendar Spreads · Butterflies · Condors · WTI/Brent",
             ha="center", color=GOLD, fontsize=9)

    # ── 1. Z-score heatmap ────────────────────────────────────────────────────
    ax_heat = fig.add_subplot(gs[0, :])
    zm = zscore_heatmap_data(signals)
    # resample to weekly for readability
    zm_w = zm.resample("W").mean()
    im = ax_heat.imshow(
        zm_w.T, aspect="auto", cmap="RdYlGn_r",
        vmin=-3, vmax=3, interpolation="nearest",
    )
    ax_heat.set_yticks(range(len(zm_w.columns)))
    ax_heat.set_yticklabels(zm_w.columns, fontsize=6.5, color=TEXT)
    # x-axis: yearly ticks
    xticks = [i for i, d in enumerate(zm_w.index) if d.month == 1]
    xlabels = [zm_w.index[i].year for i in xticks]
    ax_heat.set_xticks(xticks)
    ax_heat.set_xticklabels(xlabels, color=TEXT, fontsize=7)
    cb = plt.colorbar(im, ax=ax_heat, fraction=0.01, pad=0.005)
    cb.ax.yaxis.set_tick_params(color=TEXT, labelsize=7)
    plt.setp(cb.ax.yaxis.get_ticklabels(), color=TEXT)
    _style(ax_heat, "Z-Score Heatmap (Weekly Avg) — All Spreads")

    # ── 2–4. Individual spread charts (top 3 by trade count) ─────────────────
    top3 = per_spread.nlargest(3, "n_trades")["spread"].tolist()
    for col, (r, c) in zip(top3, [(1,0),(1,1),(1,2)]):
        ax = fig.add_subplot(gs[r, c])
        ss = signals[col]
        s  = ss.spread
        z  = ss.zscore
        sig= ss.signal

        ax2 = ax.twinx()
        ax2.plot(z.index, z, color=BLUE, lw=0.6, alpha=0.7)
        ax2.axhline( ss.z_entry, color=GREEN, ls="--", lw=0.7, alpha=0.8)
        ax2.axhline(-ss.z_entry, color=RED,   ls="--", lw=0.7, alpha=0.8)
        ax2.axhline(0, color=TEXT, lw=0.3, alpha=0.4)
        ax2.set_ylabel("Z-Score", color=BLUE, fontsize=6)
        ax2.tick_params(colors=BLUE, labelsize=6)
        ax2.set_facecolor(PANEL)
        for sp in ax2.spines.values():
            sp.set_color(GRID)

        ax.plot(s.index, s, color=GOLD, lw=0.9, label=col)
        ax.fill_between(s.index, s, s.mean(),
                        where=(sig ==  1), color=GREEN, alpha=0.15)
        ax.fill_between(s.index, s, s.mean(),
                        where=(sig == -1), color=RED,   alpha=0.15)
        ax.set_ylabel("$/bbl", color=GOLD, fontsize=6)
        ax.tick_params(colors=GOLD, labelsize=6)
        ax.set_facecolor(PANEL)
        for sp in ax.spines.values():
            sp.set_color(GRID)
        ax.set_title(col.replace("_"," ").title(), color=TEXT,
                     fontsize=8, pad=4, fontweight="bold")
        ax.grid(True, color=GRID, lw=0.3, alpha=0.6)

    # ── 5. Portfolio equity curve ─────────────────────────────────────────────
    ax_eq = fig.add_subplot(gs[2, :2])
    ax_eq.plot(equity.index, equity / 1e6, color=GREEN, lw=1.2)
    ax_eq.axhline(equity.iloc[0] / 1e6, color=TEXT, ls="--", lw=0.5, alpha=0.5)
    ax_eq.set_ylabel("Equity ($M)", color=TEXT)
    _style(ax_eq, "Portfolio Equity Curve")

    # ── 6. Drawdown ───────────────────────────────────────────────────────────
    ax_dd = fig.add_subplot(gs[2, 2])
    dd = _dd_series(equity) * 100
    ax_dd.fill_between(dd.index, dd, 0, color=RED, alpha=0.45)
    ax_dd.plot(dd.index, dd, color=RED, lw=0.6)
    ax_dd.set_ylabel("Drawdown (%)")
    _style(ax_dd, "Portfolio Drawdown")

    # ── 7. Per-spread P&L bar ─────────────────────────────────────────────────
    ax_bar = fig.add_subplot(gs[3, :2])
    ps = per_spread.copy()
    colors = [GREEN if v > 0 else RED for v in ps["total_pnl"]]
    bars = ax_bar.bar(ps["spread"], ps["total_pnl"] / 1e3, color=colors, width=0.6)
    ax_bar.axhline(0, color=TEXT, lw=0.5)
    ax_bar.set_ylabel("Net PnL ($K)")
    ax_bar.set_xticklabels(ps["spread"], rotation=35, ha="right", fontsize=7)
    _style(ax_bar, "Net P&L by Spread ($K)")

    # ── 8. Trade PnL distribution ─────────────────────────────────────────────
    ax_hist = fig.add_subplot(gs[3, 2])
    pnls  = [t.pnl_net for t in trades]
    wins  = [p for p in pnls if p > 0]
    losses= [p for p in pnls if p <= 0]
    ax_hist.hist([w / 1e3 for w in wins],   bins=20, color=GREEN, alpha=0.7,
                 label=f"Win ({len(wins)})")
    ax_hist.hist([l / 1e3 for l in losses], bins=20, color=RED,   alpha=0.7,
                 label=f"Loss ({len(losses)})")
    ax_hist.axvline(0, color=TEXT, lw=0.8)
    ax_hist.set_xlabel("Net PnL ($K)")
    ax_hist.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT)
    _style(ax_hist, "Trade PnL Distribution")

    # ── 9. Monthly returns heatmap ────────────────────────────────────────────
    ax_mr = fig.add_subplot(gs[4, :])
    mr    = monthly_returns(equity)
    im2   = ax_mr.imshow(mr.values * 100, cmap="RdYlGn",
                          aspect="auto", vmin=-5, vmax=5)
    ax_mr.set_xticks(range(len(mr.columns)))
    ax_mr.set_xticklabels(mr.columns, color=TEXT, fontsize=8)
    ax_mr.set_yticks(range(len(mr.index)))
    ax_mr.set_yticklabels(mr.index, color=TEXT, fontsize=8)
    for r in range(len(mr.index)):
        for c in range(len(mr.columns)):
            v = mr.values[r, c]
            if not np.isnan(v):
                ax_mr.text(c, r, f"{v*100:.1f}%", ha="center", va="center",
                           color="white", fontsize=6)
    cb2 = plt.colorbar(im2, ax=ax_mr, fraction=0.01, pad=0.005)
    cb2.ax.yaxis.set_tick_params(color=TEXT, labelsize=7)
    plt.setp(cb2.ax.yaxis.get_ticklabels(), color=TEXT)
    _style(ax_mr, "Monthly Returns (%)")

    # ── 10. Stats box ─────────────────────────────────────────────────────────
    ax_stats = fig.add_subplot(gs[5, :])
    ax_stats.axis("off")
    col_keys = list(stats.keys())
    half = len(col_keys) // 2
    left  = "\n".join(f"{k:<22} {stats[k]}" for k in col_keys[:half])
    right = "\n".join(f"{k:<22} {stats[k]}" for k in col_keys[half:])
    for x, text in [(0.02, left), (0.52, right)]:
        ax_stats.text(x, 0.95, text, transform=ax_stats.transAxes,
                      fontsize=8.5, color=TEXT, va="top", fontfamily="monospace",
                      bbox=dict(boxstyle="round,pad=0.4", facecolor=PANEL,
                                edgecolor=GRID, alpha=0.9))

    plt.savefig(save_path, dpi=150, bbox_inches="tight",
                facecolor=DARK, edgecolor="none")
    plt.close()
    print(f"Dashboard saved → {save_path}")


def plot_spread_detail(ss: SpreadSignal, trades_for_spread: list,
                       save_path: str = None):
    """Detailed single-spread chart with entry/exit annotations."""
    fig, axes = plt.subplots(3, 1, figsize=(16, 10), facecolor=DARK,
                             gridspec_kw={"height_ratios": [3, 1.5, 1]})
    fig.suptitle(f"Spread Detail: {ss.name}", color=TEXT, fontsize=12, fontweight="bold")

    # Price
    ax = axes[0]
    _style(ax, "")
    mu  = ss.spread.rolling(ss.lookback).mean()
    std = ss.spread.rolling(ss.lookback).std()
    ax.plot(ss.spread.index, ss.spread, color=GOLD, lw=0.9)
    ax.plot(mu.index, mu,        color=TEXT,  lw=0.6, ls="--", alpha=0.6)
    ax.fill_between(ss.spread.index,
                    mu - ss.z_entry * std, mu + ss.z_entry * std,
                    alpha=0.1, color=BLUE)
    for t in trades_for_spread:
        c = GREEN if t.direction == 1 else RED
        ax.axvline(t.entry_date, color=c,    lw=0.5, alpha=0.6)
        if t.exit_date:
            ax.axvline(t.exit_date, color=TEXT, lw=0.4, alpha=0.4)
    ax.set_ylabel("$/bbl", color=TEXT)

    # Z-score
    ax2 = axes[1]
    _style(ax2, "")
    ax2.plot(ss.zscore.index, ss.zscore, color=BLUE, lw=0.7)
    ax2.axhline( ss.z_entry, color=GREEN, ls="--", lw=0.8)
    ax2.axhline(-ss.z_entry, color=RED,   ls="--", lw=0.8)
    ax2.axhline(0, color=TEXT, lw=0.3)
    ax2.fill_between(ss.zscore.index, ss.zscore, 0,
                     where=ss.zscore < -ss.z_entry, color=GREEN, alpha=0.2)
    ax2.fill_between(ss.zscore.index, ss.zscore, 0,
                     where=ss.zscore >  ss.z_entry, color=RED,   alpha=0.2)
    ax2.set_ylabel("Z-Score", color=TEXT)

    # Signal
    ax3 = axes[2]
    _style(ax3, "")
    ax3.bar(ss.signal.index, ss.signal,
            color=ss.signal.map({1: GREEN, -1: RED, 0: GRID}), width=1.5)
    ax3.set_yticks([-1, 0, 1])
    ax3.set_yticklabels(["Short", "Flat", "Long"], color=TEXT, fontsize=7)
    ax3.set_ylabel("Signal", color=TEXT)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=130, bbox_inches="tight",
                    facecolor=DARK, edgecolor="none")
        plt.close()
    else:
        plt.show()
