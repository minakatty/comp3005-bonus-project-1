#!/usr/bin/env python3
"""
Section 8.3: run R join[R.b=S.b] S at each size and record comparisons, wall
time and output size. Also measures select and project alone, for 8.4 Q3.

    python bench.py --sizes 1000 2000 4000 8000 16000 32000 64000

writes results.csv with columns:
    n, m, join_comparisons, join_time_s, join_output_tuples,
    select_examined, select_time_s, project_time_s

This does NOT write REPORT.md itself -- Section 8.4 asks for your own
explanation of these numbers, in your own words, and that has to be written
by whoever is going to defend it in the oral check.

Warning: the whole point of Section 8 is that the nested-loop join is
quadratic, so the last couple of sizes are genuinely slow -- n=m=64000 is
about 4.1 billion comparisons pairs, on the order of tens of minutes in
CPython. Run it once, let it finish, don't rerun it lightly.
"""

import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gen_data import generate, write_relation                  # noqa: E402
from ralang.catalog import parse_catalog                       # noqa: E402
from ralang.instrument import Counters                         # noqa: E402
from ralang.operators import evaluate                          # noqa: E402
from ralang.parser import parse_query                           # noqa: E402


def build_catalog_source(r_rows, s_rows) -> str:
    lines = ["R (a, b) = {"]
    lines += [f"{a}, {b}" for a, b in r_rows]
    lines.append("}")
    lines.append("S (b, c) = {")
    lines += [f"{b}, {c}" for b, c in s_rows]
    lines.append("}")
    return "\n".join(lines) + "\n"


def run_one(n: int, m: int, match_rate: float, seed: int) -> dict:
    r_rows, s_rows = generate(n, m, match_rate, seed)
    source = build_catalog_source(r_rows, s_rows)
    catalog = parse_catalog(source)

    # Join
    counters = Counters()
    t0 = time.perf_counter()
    node = parse_query("R join[R.b=S.b] S")
    rel = evaluate(node, catalog, counters)
    join_time = time.perf_counter() - t0

    # Select alone, over R, same order of magnitude of work as a fair
    # comparison point for 8.4 Q3.
    sel_counters = Counters()
    t0 = time.perf_counter()
    sel_node = parse_query("select[a>=0](R)")
    evaluate(sel_node, catalog, sel_counters)
    select_time = time.perf_counter() - t0

    # Project alone, over R.
    t0 = time.perf_counter()
    proj_node = parse_query("project[a](R)")
    evaluate(proj_node, catalog, Counters())
    project_time = time.perf_counter() - t0

    return {
        "n": n, "m": m,
        "join_comparisons": counters.comparisons,
        "join_time_s": round(join_time, 6),
        "join_output_tuples": len(rel.rows),
        "select_examined": sel_counters.examined,
        "select_time_s": round(select_time, 6),
        "project_time_s": round(project_time, 6),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", type=int, nargs="+",
                    default=[1000, 2000, 4000, 8000, 16000, 32000, 64000])
    ap.add_argument("--match-rate", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="results.csv")
    args = ap.parse_args()

    rows = []
    for size in args.sizes:
        print(f"running n=m={size} ...", flush=True)
        row = run_one(size, size, args.match_rate, args.seed)
        rows.append(row)
        print(f"  comparisons={row['join_comparisons']:,}  "
              f"time={row['join_time_s']:.3f}s  "
              f"output={row['join_output_tuples']:,}", flush=True)

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
