"""
Evaluates a parsed AST against a catalog of loaded relations.

Each operator maps directly onto Section 4.3's table. `join[c]` is not a
separate implementation: it calls the same `_times` and `_select_rows`
helpers `times` and `select` use, in that order, because the spec defines it
that way ("Defined as times followed by select[c]") and building it literally
that way means it can never quietly drift from a bare times+select giving a
different answer.

Two static checks run before any row is touched, both raising positioned
errors rather than ever reaching a stack trace:
  * `Schema.resolve` / `Schema.concat` / `union_compatible_with` -- name and
    schema errors (unknown attribute, ambiguous attribute, arity/name/type
    mismatch, qualified-name collision)
  * `_check_condition_types` -- walks a condition once against a schema and
    raises a Type error before the first row is examined, so a query like
    `select[Age>'30'](R)` never produces a silently-false row; it fails
    up front.
"""

import operator as _op
from typing import Dict, List

from . import ast_nodes as ast
from .errors import NameError_, SchemaError, TypeError_
from .instrument import Counters
from .relation import Relation, Row, dedup
from .schema import ColType, Schema

_COMPARE_FNS = {
    "EQ": _op.eq, "NE": _op.ne, "LT": _op.lt,
    "LE": _op.le, "GT": _op.gt, "GE": _op.ge,
}


# ==========================================================================
# Conditions
# ==========================================================================

def _operand_type(operand: ast.Node, schema: Schema):
    if isinstance(operand, ast.Num):
        return ColType.NUMBER
    if isinstance(operand, ast.Str):
        return ColType.STRING
    if isinstance(operand, ast.Attr):
        return schema.types[schema.resolve(operand)]
    raise AssertionError(f"unhandled operand {type(operand).__name__}")


def _check_condition_types(cond: ast.Node, schema: Schema) -> None:
    """Static pass: resolve every attribute and reject any number/string
    comparison before a single row is examined."""
    if isinstance(cond, (ast.And, ast.Or)):
        _check_condition_types(cond.left, schema)
        _check_condition_types(cond.right, schema)
        return
    if isinstance(cond, ast.Not):
        _check_condition_types(cond.inner, schema)
        return
    if isinstance(cond, ast.Compare):
        lt = _operand_type(cond.left, schema)
        rt = _operand_type(cond.right, schema)
        if lt != rt:
            raise TypeError_(
                f"cannot compare a {lt.value} to a {rt.value}: "
                f"{cond.label()}", *cond.pos)
        return
    raise AssertionError(f"unhandled condition {type(cond).__name__}")


def _operand_value(operand: ast.Node, row: Row, schema: Schema):
    if isinstance(operand, ast.Num):
        return operand.value
    if isinstance(operand, ast.Str):
        return operand.value
    if isinstance(operand, ast.Attr):
        return row[schema.resolve(operand)]
    raise AssertionError(f"unhandled operand {type(operand).__name__}")


def _eval_condition(cond: ast.Node, row: Row, schema: Schema) -> bool:
    if isinstance(cond, ast.And):
        return (_eval_condition(cond.left, row, schema)
                and _eval_condition(cond.right, row, schema))
    if isinstance(cond, ast.Or):
        return (_eval_condition(cond.left, row, schema)
                or _eval_condition(cond.right, row, schema))
    if isinstance(cond, ast.Not):
        return not _eval_condition(cond.inner, row, schema)
    if isinstance(cond, ast.Compare):
        lv = _operand_value(cond.left, row, schema)
        rv = _operand_value(cond.right, row, schema)
        return _COMPARE_FNS[cond.op](lv, rv)
    raise AssertionError(f"unhandled condition {type(cond).__name__}")


# ==========================================================================
# Operators
# ==========================================================================

def _select_rows(cond: ast.Node, relation: Relation,
                 counters: Counters) -> Relation:
    _check_condition_types(cond, relation.schema)
    kept: List[Row] = []
    for row in relation.rows:
        counters.examined += 1                 # Section 8.2
        if _eval_condition(cond, row, relation.schema):
            kept.append(row)
    return Relation(relation.schema, kept)


def _project(node: ast.Project, child: Relation) -> Relation:
    indices: List[int] = []
    seen: Dict[str, ast.Attr] = {}
    for a in node.attrs:
        idx = child.schema.resolve(a)
        label = child.schema.attrs[idx].qualified()
        if label in seen:
            # Case 24: documented choice -- a repeated attribute in one
            # project list is an error, not silently collapsed to one column.
            raise SchemaError(
                f"'{a.qualified()}' appears more than once in this "
                f"projection", *a.pos)
        seen[label] = a
        indices.append(idx)

    schema = child.schema.project(indices)
    rows = [tuple(row[i] for i in indices) for row in child.rows]
    return Relation(schema, dedup(rows))        # case 23: dedup after projecting


def _union(node: ast.Node, left: Relation, right: Relation) -> Relation:
    left.schema.union_compatible_with(right.schema, node.pos)
    return Relation(left.schema, dedup(left.rows + right.rows))


def _intersect(node: ast.Node, left: Relation, right: Relation) -> Relation:
    left.schema.union_compatible_with(right.schema, node.pos)
    right_set = set(right.rows)
    return Relation(left.schema, [r for r in left.rows if r in right_set])


def _minus(node: ast.Node, left: Relation, right: Relation) -> Relation:
    left.schema.union_compatible_with(right.schema, node.pos)
    right_set = set(right.rows)
    return Relation(left.schema, [r for r in left.rows if r not in right_set])


def _times(node: ast.Node, left: Relation, right: Relation,
          counters: Counters) -> Relation:
    schema = Schema.concat(left.schema, right.schema, node.pos)
    rows: List[Row] = []
    # The nested loop the spec expects. Every pair generated here is one
    # comparison, counted whether or not a `join` condition will later keep
    # or discard it -- which is what makes the count exactly n * m.
    for lrow in left.rows:
        for rrow in right.rows:
            counters.comparisons += 1           # Section 8.2
            rows.append(lrow + rrow)
    # No dedup needed here: both inputs are already duplicate-free (that
    # invariant is maintained by every operator), the schemas were checked
    # disjoint above, and two distinct pairs of rows can only concatenate to
    # the same tuple if both halves were already equal -- so the result
    # inherits set semantics for free. See relation.py's dedup docstring.
    return Relation(schema, rows)


def evaluate(node: ast.Node, catalog: Dict[str, Relation],
            counters: Counters) -> Relation:
    if isinstance(node, ast.Relation):
        if node.name not in catalog:
            raise NameError_(f"unknown relation '{node.name}'", *node.pos)
        return catalog[node.name]

    if isinstance(node, ast.Select):
        child = evaluate(node.child, catalog, counters)
        return _select_rows(node.cond, child, counters)

    if isinstance(node, ast.Project):
        return _project(node, evaluate(node.child, catalog, counters))

    if isinstance(node, ast.Rename):
        child = evaluate(node.child, catalog, counters)
        return Relation(child.schema.renamed(node.new_name), child.rows)

    if isinstance(node, ast.Union):
        return _union(node, evaluate(node.left, catalog, counters),
                     evaluate(node.right, catalog, counters))
    if isinstance(node, ast.Intersect):
        return _intersect(node, evaluate(node.left, catalog, counters),
                          evaluate(node.right, catalog, counters))
    if isinstance(node, ast.Minus):
        return _minus(node, evaluate(node.left, catalog, counters),
                     evaluate(node.right, catalog, counters))

    if isinstance(node, ast.Times):
        return _times(node, evaluate(node.left, catalog, counters),
                     evaluate(node.right, catalog, counters), counters)

    if isinstance(node, ast.Join):
        # Literally times, then select -- see the module docstring.
        product = _times(node, evaluate(node.left, catalog, counters),
                         evaluate(node.right, catalog, counters), counters)
        return _select_rows(node.cond, product, counters)

    raise AssertionError(f"unhandled node type {type(node).__name__}")


# ==========================================================================
# Printing (case 19's distinguishable columns, case 25's empty result)
# ==========================================================================

def format_relation(rel: Relation) -> str:
    counts: Dict[str, int] = {}
    for a in rel.schema.attrs:
        counts[a.name] = counts.get(a.name, 0) + 1

    def label(a):
        # Qualify only where a bare name would be ambiguous in the header --
        # e.g. two columns both called DID after `Emp join[...] Dept`.
        return a.qualified() if counts[a.name] > 1 else a.name

    header = " | ".join(label(a) for a in rel.schema.attrs)
    lines = [header, "-" * len(header)]
    for row in rel.rows:
        lines.append(" | ".join(str(v) for v in row))
    if not rel.rows:
        lines.append("(0 tuples)")
    return "\n".join(lines)
