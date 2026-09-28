#!/usr/bin/env python3
"""
Section 8.4 Q2: plot time against n on log-log axes, and report the fitted slope.

    python tools/plot.py results.csv

Needs matplotlib (allowed for the report only):  pip install matplotlib
Writes results_loglog.png next to the CSV. The slope is a least-squares fit of
log10(time) against log10(n), computed here by hand so the number in the report
can be traced to these few lines.
"""

import csv
import math
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def fit_slope(xs, ys):
    lx = [math.log10(v) for v in xs]
    ly = [math.log10(v) for v in ys]
    mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
    slope = (sum((a - mx) * (b - my) for a, b in zip(lx, ly))
             / sum((a - mx) ** 2 for a in lx))
    return slope, my - slope * mx


def main(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    n = [int(r["n"]) for r in rows]
    series = {
        "join": [float(r["join_time_s"]) for r in rows],
        "select": [float(r["select_time_s"]) for r in rows],
        "project": [float(r["project_time_s"]) for r in rows],
    }

    fig, ax = plt.subplots(figsize=(7, 5))
    for name, ys in series.items():
        slope, _ = fit_slope(n, ys)
        ax.loglog(n, ys, marker="o", label=f"{name} (slope {slope:.2f})")
        print(f"{name}: slope = {slope:.3f}")

    # Reference line with slope exactly 2, anchored at the first join point.
    ref = [series["join"][0] * (v / n[0]) ** 2 for v in n]
    ax.loglog(n, ref, "k--", linewidth=1, label="slope 2 reference")

    ax.set_xlabel("n (tuples per relation)")
    ax.set_ylabel("wall time (s)")
    ax.set_title("Time vs n, log-log")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    out = path.rsplit(".", 1)[0] + "_loglog.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results.csv")
