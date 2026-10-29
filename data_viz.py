#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoC "Edge vs Cloud in 5G" - data aggregation and post-processing.

Reads telemetry.csv (columns: timestamp, profile_type, latency_ms,
throughput_mbps) into a pandas DataFrame and produces two publication-ready
charts (matplotlib, Agg backend - works headless):

  1) latency_plot.png     - boxplot of latency per traffic type.
                            The spread of the box (IQR) visualises variance /
                            jitter, which is the key acceptance criterion for
                            URLLC services.
  2) throughput_plot.png  - bar chart of the mean throughput per traffic type,
                            with standard deviation as error bars.

Additionally a statistical summary (mean, median, std = jitter, p95) is
printed to the console, ready to be quoted in the thesis.

Run:       python data_viz.py
Requires:  pip install pandas matplotlib
"""

import os

import matplotlib
matplotlib.use("Agg")  # generate to files; works also without a GUI/display
import matplotlib.pyplot as plt
import pandas as pd

# ====================== CONFIGURATION ======================
CSV_FILE       = "telemetry.csv"
LATENCY_PNG    = "latency_plot.png"
THROUGHPUT_PNG = "throughput_plot.png"
DPI            = 200

PROFILE_ORDER  = ["URLLC_Sensor", "eMBB_Video"]
PROFILE_COLORS = {"URLLC_Sensor": "#2e86de",   # blue - cloud-independent URLLC
                  "eMBB_Video":   "#ee5253"}   # red  - bandwidth-hungry eMBB
# ===========================================================


def load_results(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise SystemExit(f"File '{path}' does not exist. Run ue_client.py first to make the measurement.")
    df = pd.read_csv(path)
    # empty rows (failed queries) -> NaN -> automatically excluded from statistics
    df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")
    df["throughput_mbps"] = pd.to_numeric(df["throughput_mbps"], errors="coerce")
    return df


def print_summary(df: pd.DataFrame, profiles) -> None:
    lat = df.groupby("profile_type")["latency_ms"].describe().round(2)
    thr = (df.groupby("profile_type")["throughput_mbps"]
             .agg(["mean", "std", "min", "max"]).round(2))
    print("\n=== LATENCY summary [ms] ('std' column = jitter) ===")
    print(lat.to_string())
    print("\n=== THROUGHPUT summary [Mbps] ===")
    print(thr.to_string() + "\n")


def make_latencies_boxplot(df: pd.DataFrame, profiles, colors) -> None:
    """Boxplot of latency - shows average, median AND the real dispersion (jitter)."""
    data, positions, labels = [], [], []
    for i, profile in enumerate(profiles, start=1):
        values = df.loc[df["profile_type"] == profile, "latency_ms"].dropna().to_list()
        if values:
            data.append(values)
            positions.append(i)
            labels.append(f"{profile}\n(n={len(values)})")
    if not data:
        raise SystemExit("No latency data in telemetry.csv.")

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    bp = ax.boxplot(data, positions=positions, widths=0.45, patch_artist=True,
                    showmeans=True, meanprops=dict(marker="D", markerfacecolor="white",
                                                   markeredgecolor="black", markersize=6),
                    medianprops=dict(color="black", linewidth=1.6),
                    flierprops=dict(marker="o", markersize=4, alpha=0.5))
    for patch, profile in zip(bp["boxes"], [p for p in profiles
                                            if (df["profile_type"] == p).any()]):
        patch.set_facecolor(colors[profile])
        patch.set_alpha(0.30)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Latency [ms]")
    ax.set_title("URLLC (Edge) vs eMBB (Cloud) - latency distribution (boxplot)")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(LATENCY_PNG, dpi=DPI)
    plt.close(fig)
    print(f"[ok] saved: {LATENCY_PNG}", flush=True)


def make_throughput_barplot(df: pd.DataFrame, profiles, colors) -> None:
    """Bar chart of the MEAN throughput, with standard deviation as error bars."""
    stats = (df.groupby("profile_type")["throughput_mbps"]
               .agg(["mean", "std"])
               .reindex(profiles))
    stats = stats.dropna(how="all")
    if stats.empty:
        raise SystemExit("No throughput data in telemetry.csv.")

    present = [p for p in profiles if p in stats.index]
    cols = [colors[p] for p in present]

    fig, ax = plt.subplots(figsize=(6.0, 5.0))
    bars = ax.bar(present, stats.loc[present, "mean"], width=0.5,
                  yerr=stats.loc[present, "std"].fillna(0.0), capsize=8,
                  color=cols, alpha=0.85)
    ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=11)

    ax.set_ylabel("Average throughput [Mbps]")
    ax.set_title("URLLC (Edge) vs eMBB (Cloud) - average throughput (1 MB payload)")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(THROUGHPUT_PNG, dpi=DPI)
    plt.close(fig)
    print(f"[ok] saved: {THROUGHPUT_PNG}", flush=True)


def main() -> None:
    df = load_results(CSV_FILE)
    print_summary(df, PROFILE_ORDER)
    make_latencies_boxplot(df, PROFILE_ORDER, PROFILE_COLORS)
    make_throughput_barplot(df, PROFILE_ORDER, PROFILE_COLORS)
    print("All charts generated successfully.")


if __name__ == "__main__":
    main()
