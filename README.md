# Relational Algebra Engine

A from-scratch relational algebra interpreter: hand-written tokenizer, hand-written
recursive-descent parser, six operators, and no libraries doing the relational or
parsing work for it. Built to the grammar in `GRAMMAR.md`.

## Running it

```
python ra.py --tokens "select[Age>=30](R)"
python ra.py --tree   "project[Name](select[Age>30](Employees))"
python ra.py --run    "project[DID](Employees)" --data data/employees.ra
```

`--run` accepts one or more `--data` files; relations from every file are loaded
into the same catalog, so a query can join across files.

```
python -m unittest discover -s tests
```

## What's supported

- The full concrete syntax of Section 4: relation definitions; `select`, `project`,
  `rename`; `union`, `intersect`, `minus`, `times`, `join[cond]`; conditions with
  `and`/`or`/`not`/parentheses and qualified attribute references (`Emp.DID`).
- All 25 required test cases (`tests/test_tokenizer.py`, `tests/test_parser.py`,
  `tests/test_operators.py`).
- Five error categories, each raised as a positioned, rendered message and never
  as a Python traceback: `LexicalError`, `SyntaxError_`, `NameError_`,
  `SchemaError`, `TypeError_` (see `ralang/errors.py`).
- The data generator and comparison/examination instrumentation for the
  performance study (`tools/gen_data.py`, `tools/bench.py`).

## Project layout

```
ra.py                CLI: --tree, --tokens, --run
ralang/
  tokenizer.py        hand-written scanner (Section 6.1)
  ast_nodes.py         AST + parse-tree printer (Section 6.2)
  parser.py            recursive descent (Section 5.4)
  errors.py            the five error categories (Section 6.3)
  schema.py            Attribute/Schema: name resolution, type/arity checks
  relation.py           Relation + the project's own definition of tuple equality
  catalog.py             parses relation-definition files (Section 4.1)
  operators.py            the six operators + condition evaluation (Section 4.3)
  instrument.py            Section 8.2 counters
tools/
  gen_data.py          data generator (Section 8.1)
  bench.py             sweep runner (Section 8.3)
tests/                 all 25 required cases, plus edge cases
data/employees.ra      the worked example from Section 4.1
```

## Design decisions the spec leaves to the implementer

**Case 8 — keywords that are also attribute names.** The tokenizer never
reserves a word; every word-shaped token is `IDENT`. The parser decides whether
an `IDENT` is an operator or an attribute purely by grammatical position:
in an operand position it is always an attribute, in an operator position it
is always the operator. Consequence: `select[union=3](R)` works, but a relation
literally named `union` cannot be the left operand of `A union B` without
parentheses, because at that position the parser is looking for an operator
first. See `GRAMMAR.md` §5.3 for the full reasoning, including the one place
(`not`) where this needed a single token of lookahead.

**Case 24 — `project[Name, Name](R)`.** Decision: **error**, not silent
collapse. A repeated attribute in one projection list is rejected
(`SchemaError`) rather than quietly producing a one-column result, because a
query that asks for two columns and silently gets one is exactly the kind of
"silently wrong answer" the spec elsewhere goes out of its way to avoid
(Section 4.3's note on union compatibility makes the same call). See
`ralang/operators.py::_project`.

**Column types are decided once, at load time.** Every value in a column of a
base relation must be the same kind (number or string); this is checked when
the relation is parsed from its definition (`ralang/catalog.py`), not
re-derived on every query. `select[Age>'30'](Employees)` (case 22) is then a
simple lookup against `Age`'s stored type, not a per-row inference.

**Ambiguous unqualified attributes.** After `times`/`join`, an unqualified
attribute name that exists on both sides is a `NameError_` telling you to
qualify it, not a guess at which side was meant.

## Why case 20 needs `rename`

`Emp join[Emp.MgrID=E2.EID] Emp` — joining `Emp` against itself directly — is
unanswerable as written, for a structural reason, not a missing feature:
`join` is defined as `times` followed by `select` (Section 4.3), and `times`
qualifies every attribute by the name of the relation it came from. If both
sides of the `times` are literally `Emp`, both sides produce the *same*
qualified name for every attribute (`Emp.EID`, `Emp.Name`, ...), and
`ralang/schema.py::Schema.concat` rejects that collision before the join
condition is ever evaluated. The condition `Emp.MgrID = Emp.EID` can only
mean something once the two occurrences of `Emp` are distinguishable, and
qualification is the only mechanism the language has for telling two
attributes apart — hence `rename[E2](Emp)` first, which relabels every
attribute's owning relation from `Emp` to `E2` without changing the data or
the attribute names. After that, `times` produces `Emp.EID`/`E2.EID`, and the
condition is well-defined. This is also why `Schema.concat`'s collision check
matters beyond case 20: it is the same mechanism that catches an accidental
`R times R` anywhere else in a query.

## Known limitations

- Nulls, query optimization, indexes and non-nested-loop join strategies are
  out of scope, per Section 3.
- A base relation's column type is fixed at load time from the values present
  in its definition; the engine does not support a column that legitimately
  mixes numbers and strings (documented above, and enforced with a
  `SchemaError` at load time rather than a confusing failure later).
- Error recovery is single-shot: parsing stops at the first error rather than
  collecting several. Given the query language's size this seemed like the
  right trade for message clarity over resilience, but it is a real
  simplification worth naming.

## Performance

See `REPORT.md` for the full sweep, methodology and analysis. Fair warning if
you rerun it: the join is the intentionally-quadratic nested loop the spec
asks for, so the largest size in the required sweep (n = m = 64000, about
4.1 billion compared pairs) takes on the order of an hour in CPython — this
was measured by timing the same code at smaller sizes and extrapolating
before running it for real, which is itself one of the report's own
questions (Section 8.4 Q4) answered in miniature.
