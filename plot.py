#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Edge vs Cloud PoC - visualization of measurement results.

Reads results.csv (columns: timestamp, server_type, latency_ms, throughput_mbps)
and generates two PNG files:

  1) latency_boxplot.png  - boxplot of latency Edge vs Cloud
                            (shows the average, median AND jitter/dispersion)
  2) throughput_bars.png  - bar chart with the mean throughput Edge vs Cloud

In the console it additionally prints a statistical summary
(mean, median, std-dev = jitter, percentiles) useful for the thesis.

Run:       python plot.py
Requires:  pip install pandas matplotlib
"""

import os
import random

import matplotlib
matplotlib.use("Agg")  # generate to files; works also without a GUI/display
import matplotlib.pyplot as plt
import pandas as pd

# ====================== CONFIGURATION ======================
CSV_FILE    = "results.csv"
BOXPLOT_PNG = "latency_boxplot.png"
BARPLOT_PNG = "throughput_bars.png"
DPI         = 200

EDGE_COLOR  = "#2e86de"  # blue
CLOUD_COLOR = "#ee5253"  # red
# ===========================================================


def load_results(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise SystemExit(f"File '{path}' does not exist. Run client.py first to make the measurement.")
    df = pd.read_csv(path)
    # empty rows (failed queries) -> NaN -> automatically excluded from the statistics
    df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")
    df["throughput_mbps"] = pd.to_numeric(df["throughput_mbps"], errors="coerce")
    return df


def print_summary(df: pd.DataFrame) -> None:
    lat = df.groupby("server_type")["latency_ms"].describe().round(2)
    thr = (df.groupby("server_type")["throughput_mbps"]
             .agg(["mean", "std", "min", "max"]).round(2))
    print("\n=== LATENCY summary [ms] ('std' column = jitter) ===")
    print(lat.to_string())
    print("\n=== THROUGHPUT summary [Mbps] ===")
    print(thr.to_string() + "\n")


def make_boxplot(df: pd.DataFrame) -> None:
    """Boxplot of latency - shows average, median AND the real dispersion (jitter)."""
    edge  = df.loc[df["server_type"] == "Edge",  "latency_ms"].dropna().to_list()
    cloud = df.loc[df["server_type"] == "Cloud", "latency_ms"].dropna().to_list()

    # build the plot only from the environments that actually have data
    data, positions, colors, labels = [], [], [], []
    for name, color, values in (("Edge", EDGE_COLOR, edge), ("Cloud", CLOUD_COLOR, cloud)):
        if values:
            data.append(values)
            positions.append(len(data))
            colors.append(color)
            labels.append(f"{name}\n(n={len(values)})")
    if not data:
        raise SystemExit("No latency data in results.csv.")

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    bp = ax.boxplot(data, positions=positions, widths=0.45, patch_artist=True,
                    showmeans=True, meanprops=dict(marker="D", markerfacecolor="white",
                                                   markeredgecolor="black", markersize=6),
                    medianprops=dict(color="black", linewidth=1.6),
                    flierprops=dict(marker="o", markersize=4, alpha=0.5))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.30)

    # raw measurement points (jitter) drawn over the boxplot
    rng = random.Random(42)  # fixed seed -> reproducible plot
    for pos, values, color in zip(positions, data, colors):
        xs = [pos + rng.uniform(-0.12, 0.12) for _ in values]
        ax.scatter(xs, values, s=14, alpha=0.45, color=color, edgecolors="none", zorder=3)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Latency [ms]")
    ax.set_title("Edge vs Cloud - latency distribution (boxplot + jitter)")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(BOXPLOT_PNG, dpi=DPI)
    plt.close(fig)
    print(f"[ok] saved: {BOXPLOT_PNG}", flush=True)


def make_barplot(df: pd.DataFrame) -> None:
    """Bar chart of the MEAN throughput, with standard deviation as error bars."""
    stats = (df.groupby("server_type")["throughput_mbps"]
               .agg(["mean", "std"])
               .reindex(["Edge", "Cloud"])
               .dropna(how="all"))
    if stats.empty:
        raise SystemExit("No throughput data in results.csv.")

    colors = [{"Edge": EDGE_COLOR, "Cloud": CLOUD_COLOR}[name] for name in stats.index]

    fig, ax = plt.subplots(figsize=(6.0, 5.0))
    bars = ax.bar(stats.index, stats["mean"], width=0.5,
                  yerr=stats["std"].fillna(0.0), capsize=8,
                  color=colors, alpha=0.85)
    ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=11)

    ax.set_ylabel("Average throughput [Mbps]")
    ax.set_title("Edge vs Cloud - average throughput (1 MB payload)")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(BARPLOT_PNG, dpi=DPI)
    plt.close(fig)
    print(f"[ok] saved: {BARPLOT_PNG}", flush=True)


def main() -> None:
    df = load_results(CSV_FILE)
    print_summary(df)
    make_boxplot(df)
    make_barplot(df)
    print("All charts generated successfully.")


if __name__ == "__main__":
    main()
