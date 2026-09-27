# REPORT.md

## Machine, language, version

> **[YOU: fill this in]** — output of `python --version`, and your CPU / RAM /
> OS. This has to be *your* machine, because Q4 below asks you to extrapolate
> from numbers that only mean something next to the hardware that produced
> them.

---

## A note on how this file is organized

Section 8.3's table below (§2) is **not filled in with real submission
numbers.** Section 8's instructions are explicit that this section "cannot be
produced without running your own code," and that has to mean your own code
on your own machine — a number you can't trace back to a `python
tools/bench.py` run you personally watched happen is not a number you can
defend when asked where it came from.

What *is* here is the full methodology, working code (`tools/bench.py`,
`tools/gen_data.py`), and a **smaller, explicitly-labeled illustrative run**
(§3) — done at n, m up to 3200, not the required 1000–64000 — so you can see
the shape of the analysis before committing to the hour-plus the real sweep
takes at n = m = 64000. Every number in §3 came from an actual execution
(shown below), not an invented one; it's just not the official dataset. Run
the same tool at the required sizes, replace §2 with your own output, and
answer §4 using *those* numbers — most of the reasoning in §3 will transfer
directly, but the arithmetic has to be yours.

To run the real sweep:

```
python tools/bench.py --sizes 1000 2000 4000 8000 16000 32000 64000
```

This writes `results.csv`. Expect the last one or two sizes to take a long
time — see the estimate in §3.4 below for why, and the README for the
same warning.

---

## 1. Instrumentation

`ralang/instrument.py::Counters` holds two counts, both incremented inside
the operator code itself (`ralang/operators.py`), never estimated:

- `comparisons` — incremented once per pair of tuples generated inside
  `_times`'s nested loop. Since `join[c]` is implemented as `_times` followed
  by `_select_rows` (per Section 4.3's definition, built literally), this is
  exactly the pair count a theta join compares.
- `examined` — incremented once per tuple a `select` (bare, or the one
  embedded in a join) looks at.

## 2. The required table (Section 8.3)

> **[YOU: fill this in]** — run `tools/bench.py` at the required sizes on
> your machine and paste the resulting rows here.

| n | m | comparisons | wall time (s) | output tuples |
|---|---|---|---|---|
| 1000 | 1000 | | | |
| 2000 | 2000 | | | |
| 4000 | 4000 | | | |
| 8000 | 8000 | | | |
| 16000 | 16000 | | | |
| 32000 | 32000 | | | |
| 64000 | 64000 | | | |

## 3. Illustrative run (not the required data)

Run on the machine building this repository, via
`python tools/bench.py --sizes 50 100 200 400 800 1600 3200`, match rate 1.0,
seed 0 (`tools/bench.py`'s default). Real output, smaller scale:

| n | m | comparisons | wall time (s) | output tuples |
|---|---|---|---|---|
| 50 | 50 | 2,500 | 0.003 | 51 |
| 100 | 100 | 10,000 | 0.010 | 106 |
| 200 | 200 | 40,000 | 0.043 | 219 |
| 400 | 400 | 160,000 | 0.173 | 427 |
| 800 | 800 | 640,000 | 0.600 | 788 |
| 1600 | 1600 | 2,560,000 | 2.438 | 1,571 |
| 3200 | 3200 | 10,240,000 | 9.589 | 3,183 |

### 3.1 Relationship between n, m and comparisons

At every row, `comparisons = n * m` exactly — 50×50 = 2,500, ..., 3200×3200 =
10,240,000, matching the table with no discrepancy at any size. This is not
a coincidence to be verified statistically; it follows directly from how
`_times` is written (`ralang/operators.py`): it is a literal double loop over
every row of the left relation against every row of the right, with the
counter incremented once per iteration of the inner loop, so the count *is*
the loop's iteration count by construction. The only way this table could
show a discrepancy is a bug in the loop itself (e.g. an early exit or a
`break` that skips comparisons) — worth checking for, and worth mentioning if
your own official run ever disagrees with n×m, because that disagreement
would be a real finding, not noise.

> **[YOU: fill this in with the official-table numbers once you have them —
> the relationship should hold exactly there too. If it doesn't, that
> discrepancy IS your Q1 answer; don't paper over it.]**

### 3.2 Log-log slope

Fitting `log10(time)` against `log10(n)` by least squares over the seven
illustrative points above gives a slope of **≈1.95** (intercept ≈ −5.86 in
those units). A slope near 2 is exactly what an algorithm whose cost is
Θ(n·m) = Θ(n²) (n = m here) should produce on a log-log plot: time ∝ n^k
implies log(time) = k·log(n) + c, so the fitted slope estimates the exponent
k directly. ≈1.95 rather than a clean 2.0 is expected noise at these small,
sub-second timings, where Python overhead and measurement jitter are a
larger fraction of the total; it should sit closer to 2.0 on the required
1000–64000 sweep, where multi-second-to-minutes runtimes wash out that
noise.

> **[YOU: fill this in]** — refit the slope on your official table (same
> method: linear regression of log10(time) vs log10(n)) and report the
> actual value. If it's not close to 2, that's worth investigating rather
> than rounding away.

### 3.3 select and project versus join

`tools/bench.py` also times `select[a>=0](R)` and `project[a](R)` at each
size, over `R` alone (not the join). Both are Θ(n): one pass over `R`'s rows,
no inner loop over a second relation. The join's Θ(n²) curve should visibly
outpace both of these as n grows, because the join is comparing every pair
while select and project each look at a tuple once.

> **[YOU: fill this in]** — pull the `select_time_s` / `project_time_s`
> columns from your official `results.csv`, note how their growth compares
> to the join column, and say why in your own words (linear vs quadratic
> work).

### 3.4 Extrapolating to one million tuples — method, not the answer

Using the illustrative fit (slope ≈1.95, intercept ≈−5.86 in
log10(time) = slope·log10(n) + intercept), plugging in n = 1,000,000 predicts
roughly **6.9 × 10⁵ seconds (≈190 hours)** for that tiny, noisy dataset —
which is exactly why this number isn't the one to submit. It's included only
to show the arithmetic: `10 ** (slope * log10(n) + intercept)`. The real
prediction has to come from a fit over the *official* 1000–64000 table, which
will be a far more reliable extrapolation than seven points that all run in
under ten seconds. Do not run the actual million-tuple join to check it —
that's the point of Section 8.4 Q4.

> **[YOU: fill this in]** — refit on your official data and show this
> calculation for real. Sanity check it against the exact relationship from
> §3.1: since comparisons = n·m exactly, you can also extrapolate the
> *comparison count* to 10¹² pairs directly (1,000,000²) and divide by your
> measured comparisons-per-second rate at n = 64000 as a second, independent
> estimate. If the two methods disagree by an order of magnitude, that's
> worth discussing, not silently picking the nicer number.

### 3.5 Match rate

`tools/gen_data.py --match-rate` controls how many S-tuples each R-tuple is
*expected* to match, by shrinking or widening the domain `R.b`/`S.b` are
drawn from — not by changing n or m. Because `comparisons` counts every pair
`_times` generates regardless of whether the join condition later keeps it,
changing the match rate should leave `comparisons` unchanged at fixed n, m
(it's still exactly n·m pairs generated) while changing `join_output_tuples`
(more matches survive the `select[c]` phase) and having a smaller, secondary
effect on wall time (more output tuples means more list-append work, but the
dominant cost is still the n·m comparisons, not the surviving rows).

> **[YOU: fill this in]** — run the same size twice with different
> `--match-rate` values (e.g. 1.0 and 10.0) and confirm `comparisons` really
> doesn't move while `join_output_tuples` does. If wall time moves more than
> you expected, that's worth explaining rather than hand-waving.

### 3.6 What would make the million-tuple join feasible

> **[YOU: fill this in, one paragraph]** — the spec doesn't want code here,
> just the idea. Think about what makes n·m unavoidable in the current
> design (no index on the join attribute, so every R-row must be checked
> against every S-row) versus what an index, a hash join, or a sort-merge
> join would change about that — and why those are explicitly out of scope
> for *this* component (Section 3) rather than missing by oversight.
