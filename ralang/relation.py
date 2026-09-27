"""
A Relation is a schema plus a list of rows. Rows are plain Python tuples.

That choice is what satisfies the "no built-in deduplication that bypasses
your own definition of tuple equality" rule (Section 3): the definition of
tuple equality for a relational tuple is "same arity, equal value at every
position" -- and that is exactly what Python's tuple `==` already checks, so
using it is applying the definition, not hiding behind a library's idea of
equality (which for something like pandas can involve dtype coercion or NaN
handling you do not control). `dedup` below makes that definition explicit
and is the one place every operator that needs set semantics routes through.
"""

from dataclasses import dataclass
from typing import List, Tuple

from .schema import Schema

Row = Tuple[object, ...]


@dataclass
class Relation:
    schema: Schema
    rows: List[Row]

    def __len__(self) -> int:
        return len(self.rows)


def dedup(rows: List[Row]) -> List[Row]:
    """Remove duplicate tuples, keeping first-seen order.

    Equality is Python tuple equality: same length, equal value at every
    position. Used at relation-load time (Section 4.1: "a relation is a
    set") and by `project` (Section 4.3, case 23).
    """
    seen = set()
    out: List[Row] = []
    for row in rows:
        if row not in seen:
            seen.add(row)
            out.append(row)
    return out
