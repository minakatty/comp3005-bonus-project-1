# DESIGN_LOG.md

One short entry per working session, dated. What you were trying to do, what you
tried, what broke.

**Read this before you submit:** the entries below the line marked `[session
notes]` are an honest record of what happened while this repository was built
in conversation with Claude — they are real, but they are not framed as your
personal account, and you should not submit them verbatim as if they were.
Rewrite each in your own words once you've actually read the corresponding
code and understand why the decision was made; if you can't rewrite an entry
in your own words yet, that's a sign to go read that file before the oral
check, not just before submitting the log. The entries marked `[YOU: fill
this in]` are ones only you can write, because they didn't happen to me —
they need to happen to you, while you're actually running this thing.

Grading note from the spec, repeated here so it's impossible to miss: *"A log
whose entries say that you asked an AI and it worked scores zero on this
component."* The point of this file is friction, not ceremony.

---

## [session notes] 2026-09-19 — Grammar, tokenizer, parser

**Trying to do:** get GRAMMAR.md's EBNF, precedence table and ambiguity
demonstration right before any code existed, per the two-week plan's own
instruction that the first days produce no code.

**What happened:** the first attempt at the ambiguity instance in §3.3 used
`A={1}, B={2}, C={2}`, which gives `{1}` under *both* groupings of
`A union B minus C` — it demonstrates nothing. The fix required actually
reasoning about what property an instance needs: `C` has to remove an
element that only the left-grouped tree exposes to it, i.e. an element of
`A`. `A={1}, B={2}, C={1}` was the corrected instance.

**What broke, technically:** the `not` operator in `_not_cond`
(`ralang/parser.py`) collided with the soft-keyword rule from §5.3. That rule
says position decides whether an `IDENT` is an operator or an attribute, and
that works cleanly for `and`/`or` because they only ever appear where the
parser is already looking for an infix operator. `not` is a *prefix*
operator, so it sits exactly where an operand is expected — the same
position an attribute reference would occupy. `select[not=1](R)` needs `not`
read as an attribute; `select[not (a=1)](R)` needs it read as negation. Fixed
with one token of lookahead: if the token after `not` is a comparison
operator, `not` cannot be prefix negation (nothing legal could follow it), so
it must be an attribute.

## [session notes] 2026-09-19 — Operators and schema handling

**Trying to do:** the six operators against the semantics table in §4.3,
cases 18–25.

**What broke, technically (a real AI mistake, not a hypothetical one):**
the first draft of `_infer_types` in `ralang/catalog.py` (which decides
whether a column is NUMBER or STRING when a relation is loaded) had a
condition of the form
`if not rows or kinds <= {int, float}: types.append(ColType.NUMBER if rows else ColType.STRING)`
— this conflates "the relation is empty" with "the column is numeric" in one
branch, and on a relation with rows it would still evaluate the ternary
correctly *by accident*, but the logic doesn't say what it looks like it
says and would misbehave for edge orderings. It was caught by rereading the
function before trusting it, not by a failing test (no test exercised the
empty-relation path yet at that point). Rewritten as an explicit `if empty /
elif numeric / elif string / else error` chain, which is what's in the
repository now. **This is entry #1 of your three required "AI was wrong"
occasions** — read `ralang/catalog.py::_infer_types` and the current
`tests/test_operators.py::CatalogLoading` tests, understand why the rewrite
is clearer, and write this up in your own words with your own read of the
diff.

**Decision made here, not dictated by the spec:** case 24
(`project[Name, Name](R)`) — chose "error" over "silently collapse to one
column," documented in `README.md`, enforced in
`ralang/operators.py::_project`.

---

## [YOU: fill this in] — Error handling pass (spec plan, day 10)

Once you've run all five error categories against inputs *you* constructed
(not just the ones in the test suite), note what surprised you. A good
candidate for entry #2: try feeding the parser something you're sure should
fail and see whether the error message it produces actually tells you what's
wrong, or whether you have to go read the code to understand your own
error. If an AI-suggested error message was vague, generic, or pointed at
the wrong token, that's a real entry — write down what it said, what was
wrong with it, and what you changed.

## [YOU: fill this in] — Data generator and instrumentation (day 11)

Did `tools/gen_data.py`'s match-rate parameter actually produce the match
rate you expected once you checked it empirically, or was the first version
off? That's a natural place for entry #3 — instrument it, compare, note the
discrepancy if there was one.

## [YOU: fill this in] — Running the performance sweep (day 12)

This entry has to describe *your own machine* running `tools/bench.py` up to
n = m = 64000 (see `REPORT.md`). Note how long it actually took, whether
anything (memory, patience, a laptop going to sleep) got in the way, and
whether the comparison-count formula matched exactly or needed explaining.

## [YOU: fill this in] — Finishing GRAMMAR.md and cleanup (day 13–14)

Anything that changed between your first grammar draft and what the parser
actually does, once the parser existed to check it against.
