#!/usr/bin/env python3
"""
Section 8.1: generate R(a, b) and S(b, c) at a chosen size, with a chosen
match rate between them.

    python gen_data.py --n 1000 --m 1000 --match-rate 1.0 --out data/bench

writes data/bench/R_1000.ra and data/bench/S_1000.ra.

R has n tuples, R.a = 0..n-1 (unique, so R itself has no duplicates to
collapse on load), and R.b drawn from a domain sized so that, in
expectation, each R tuple matches close to `match_rate` tuples of S under
`R.b = S.b`. S has m tuples with S.b drawn from the same domain and S.c a
distinct id per row.

Match rate is controlled by the domain size for `b`: shrinking the domain
raises the average number of S-rows each R-row's b-value collides with.
Concretely, domain_size = max(1, round(m / match_rate)), so a random S.b
value matches an R.b value with probability about match_rate / m, and each
R-row is expected to match about match_rate S-rows.
"""

import argparse
import os
import random


def generate(n: int, m: int, match_rate: float, seed: int = 0):
    rng = random.Random(seed)
    domain_size = max(1, round(m / match_rate)) if match_rate > 0 else m * 10

    r_rows = [(i, rng.randrange(domain_size)) for i in range(n)]
    s_rows = [(rng.randrange(domain_size), f"c{i}") for i in range(m)]
    return r_rows, s_rows


def write_relation(path: str, name: str, attrs, rows) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{name} ({', '.join(attrs)}) = {{\n")
        for row in rows:
            f.write(", ".join(str(v) for v in row) + "\n")
        f.write("}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, required=True, help="tuples in R")
    ap.add_argument("--m", type=int, required=True, help="tuples in S")
    ap.add_argument("--match-rate", type=float, default=1.0,
                    help="expected S-matches per R-tuple on R.b = S.b")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="data/bench", help="output directory")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    r_rows, s_rows = generate(args.n, args.m, args.match_rate, args.seed)

    r_path = os.path.join(args.out, f"R_{args.n}.ra")
    s_path = os.path.join(args.out, f"S_{args.m}.ra")
    write_relation(r_path, "R", ["a", "b"], r_rows)
    write_relation(s_path, "S", ["b", "c"], s_rows)

    print(f"wrote {r_path} ({args.n} tuples)")
    print(f"wrote {s_path} ({args.m} tuples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
