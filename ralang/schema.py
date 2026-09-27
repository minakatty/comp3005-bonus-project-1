"""
Schema: an ordered list of (owning relation, attribute name) pairs, plus a
parallel list of column types.

Two design decisions live here, both worth being able to defend:

1. Every attribute remembers which relation it came from, even after several
   operators have been stacked on top of it. That is what "Emp.DID" means at
   the far end of a query built out of select/project/join -- the tag is
   carried, not recomputed. `rename` is the only operator that changes it.

2. A column's type (NUMBER or STRING) is decided once, when a base relation
   is loaded from its definition, by requiring every value in that column to
   be the same kind (see catalog.py). It is then carried forward exactly the
   same way the relation tag is. This is a scope decision I made because the
   spec's type rule ("a comparison between a number and a string is an
   error") only makes sense if a column has one type to check against; I
   documented it here and in GRAMMAR.md rather than leaving it implicit.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List

from . import ast_nodes as ast
from .errors import NameError_, SchemaError


class ColType(str, Enum):
    NUMBER = "number"
    STRING = "string"


@dataclass(frozen=True)
class Attribute:
    relation: str
    name: str

    def qualified(self) -> str:
        return f"{self.relation}.{self.name}"


@dataclass
class Schema:
    attrs: List[Attribute]
    types: List[ColType]

    def names(self) -> List[str]:
        return [a.name for a in self.attrs]

    def resolve(self, ref: ast.Attr) -> int:
        """Return the index of the attribute `ref` refers to.

        A qualified reference (`Emp.DID`) must match both the relation tag
        and the name. An unqualified reference must be unique in the current
        schema -- if the same bare name exists under two different owning
        relations (the usual state of affairs right after `times`/`join`),
        that is a Name error telling the query to qualify it, not a guess at
        which one was meant.
        """
        pos = ref.pos

        if ref.relation is not None:
            for i, a in enumerate(self.attrs):
                if a.relation == ref.relation and a.name == ref.name:
                    return i
            raise NameError_(f"unknown attribute '{ref.qualified()}'", *pos)

        matches = [i for i, a in enumerate(self.attrs) if a.name == ref.name]
        if not matches:
            raise NameError_(f"unknown attribute '{ref.name}'", *pos)
        if len(matches) > 1:
            owners = ", ".join(self.attrs[i].qualified() for i in matches)
            raise NameError_(
                f"'{ref.name}' is ambiguous ({owners}); qualify it, "
                f"e.g. '{self.attrs[matches[0]].qualified()}'", *pos)
        return matches[0]

    def renamed(self, new_relation: str) -> "Schema":
        """rename[new](R): same attribute names, new owning relation."""
        return Schema([Attribute(new_relation, a.name) for a in self.attrs],
                      list(self.types))

    def project(self, indices: List[int]) -> "Schema":
        return Schema([self.attrs[i] for i in indices],
                      [self.types[i] for i in indices])

    @staticmethod
    def concat(left: "Schema", right: "Schema", pos) -> "Schema":
        """times: every attribute of both sides, qualified by relation.

        If a fully qualified name (relation.attribute) appears on both sides,
        that is the error Section 4.3 requires -- it is what forces
        `rename[E2](Emp) join[...] Emp` in case 20 rather than joining `Emp`
        against itself directly.
        """
        attrs = left.attrs + right.attrs
        seen = set()
        for a in attrs:
            if a.qualified() in seen:
                raise SchemaError(
                    f"'{a.qualified()}' appears on both sides of "
                    f"times/join; rename one side first", *pos)
            seen.add(a.qualified())
        return Schema(attrs, left.types + right.types)

    def union_compatible_with(self, other: "Schema", pos) -> None:
        """union/intersect/minus: same arity, same names in order, same
        types position by position. Anything else is a Schema error."""
        if len(self.attrs) != len(other.attrs):
            raise SchemaError(
                f"union/intersect/minus needs the same number of "
                f"attributes on both sides ({len(self.attrs)} vs "
                f"{len(other.attrs)})", *pos)
        for l, r in zip(self.attrs, other.attrs):
            if l.name != r.name:
                raise SchemaError(
                    f"attribute name mismatch: '{l.name}' vs '{r.name}'; "
                    f"union/intersect/minus need the same attribute names "
                    f"in the same order on both sides", *pos)
        for l, lt, rt in zip(self.attrs, self.types, other.types):
            if lt != rt:
                raise SchemaError(
                    f"type mismatch on '{l.name}': {lt.value} vs "
                    f"{rt.value}", *pos)
