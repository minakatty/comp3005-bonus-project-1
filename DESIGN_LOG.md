# Design Log

What I was tried to do, what happened, and what broke.

----

## 2026/09/25 -Getting the grammar and the first version of the code built

I spent this session getting the grammar written down first like the assignment before any code existed. I worked through the EBNF, the precedence table, and the ambiguity example with ChatGBT. One thing that actually mattered:
my first attempt at the ambiguity example used `A={1}, B={2}, C={2}`, and I almost didn't catch that it gives the same answer either way you group `A union B minus C` so it doesn't actually prove anything. The instance needs `C` to remove something that only shows up if you group `A union B` first,
which means `C` has to overlap with `A`, not `B`. That's why the real example in `GRAMMAR.md` is `A={1}, B={2}, C={1}` instead.

AI mistake #01 — the `_infer_types` bug in `ralang/catalog.py`.The first version of the function that decides whether a column is numbers or strings had a condition like `if not rows or kinds <= {int, float}: ...` that line mixes up two different checks (is the relation empty vs. is the column numeric) into one condition andd it happened to give the right answer by accident rather than for the right reason. I didn't catch this myself by running a test it came up while reading through the code before trusting it, since nothing was testing an emptyrelation column yet at that point. The fix splits it into three clear cases: no rows, all numbers,
all strings and otherwise an error. I read the before & after in `ralang/catalog.py::_infer_types` and the current tests in `tests/test_operators.py::CatalogLoading` to understand why the second version is actually correct instead of just working by luck.


##  2026/09/26— Running the required performance sweep

This is the session where Section 8.3's sweep actually ran. Two real things went wrong.

AI mistake #02— the join ran out of memory. I ran `python tools/bench.py --sizes 1000 2000 4000 8000 16000 32000 64000` and it worked fine up through n = 16000 (took about 670 seconds), then crashed at n = 32000 with a `MemoryError`, right in the middle of `_times` in `ralang/operators.py`. The problem was that the first version of `join` built the entire cross product of the two relations into a Python list
before it ever checked the join condition at n =m= 32000 that's over a billion combined rows sitting in memory at once, which is way more than my laptop has. I only found this by actually running the sweep the assignment requires it never showed up in the smaller test cases because none of them
were anywhere near that size. The fix was to check the join condition inside the same loop that generates the pairs so a pair that fails the condiition is never stored seen `_join` in `ralang/operators.py`. This didn't change the comparison count (still exactly n×m) or the answer though only how much memory it takes to compute it.



AI mistake #03 — the runtime estimate was wrong. Before I ran the fixed version, I was told the whole sweep would take "roughly an hour," based on an extrapolation from smaller test sizes. My actual run took about 98 minutes just for n =64000, and about 139 minutes for the whole thing so close to double the estimate. I found this out simply by running it and
watching the clock. Looking back at the report, the estimate came from a short run on a different, faster machine  which is exactly the kind of number that doesn't transfer between computers which is also the whole point of Section 8.4 question 4 asking me to show my extrapolation method instead of
just trusting a number


## 2026/09/27 —Writing up the report and finishing the docs



Went through `REPORT.md` using my real `results.csv` and the extra match-rate run (`results_mr10.csv`). The one thing that
surprised me here -  running the same join size (n =m= 4000) twice, once at match rate 1.0 and once at match rate 10.0, gave almost identical wall times (19.387s vs. 18.850secs) even though the output size was about ten times bigger. At first that seemed backwards, but it makes sense once I thought about theloop: the comparison count only depends on n and m, not on how many pairs match, so extra matching pairs only add a little bit of extra work (storing the result), not extra comparisons.

finished `GRAMMAR.md` section 5.5, `README.md`'s performance section with the real numbers instead of the estimate and cleaned up the repo as well (`.gitignore` for `__pycache__` and scratch files too).