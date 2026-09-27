"""
AST nodes and the parse tree printer (Section 6.2).

Two families of node:

  * expression nodes, which produce a relation  (Relation, Select, Project,
    Rename, Union, Intersect, Minus, Times, Join)
  * condition nodes, which produce a boolean    (And, Or, Not, Compare) over
    operands (Num, Str, Attr)

Only expression nodes become children in the printed tree. Conditions are
rendered inline in the parent's label, which is the format the spec shows:

    Project(attrs=[Name])
    └── Select(cond=Gt(Attr(Age), Num(30)))
        └── Relation(Employees)

Every node carries (line, col) from the token that introduced it, so a runtime
name/schema/type error can point back into the source text.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


Pos = Tuple[int, int]


# --------------------------------------------------------------------------
# Operands
# --------------------------------------------------------------------------

@dataclass
class Node:
    pass


@dataclass
class Num(Node):
    value: object
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Num({self.value})"


@dataclass
class Str(Node):
    value: str
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Str('{self.value}')"


@dataclass
class Attr(Node):
    """An attribute reference, optionally qualified as Relation.Attribute."""
    relation: Optional[str]
    name: str
    pos: Pos = (0, 0)

    def qualified(self) -> str:
        return f"{self.relation}.{self.name}" if self.relation else self.name

    def label(self) -> str:
        return f"Attr({self.qualified()})"


# --------------------------------------------------------------------------
# Conditions
# --------------------------------------------------------------------------

# Maps the token type name onto the label used in the printed tree.
COMPARE_LABEL = {
    "EQ": "Eq", "NE": "Ne", "LT": "Lt",
    "LE": "Le", "GT": "Gt", "GE": "Ge",
}


@dataclass
class Compare(Node):
    op: str                 # "EQ", "NE", "LT", "LE", "GT", "GE"
    left: Node
    right: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"{COMPARE_LABEL[self.op]}({self.left.label()}, {self.right.label()})"


@dataclass
class And(Node):
    left: Node
    right: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"And({self.left.label()}, {self.right.label()})"


@dataclass
class Or(Node):
    left: Node
    right: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Or({self.left.label()}, {self.right.label()})"


@dataclass
class Not(Node):
    inner: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Not({self.inner.label()})"


# --------------------------------------------------------------------------
# Expressions
# --------------------------------------------------------------------------

@dataclass
class Relation(Node):
    name: str
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Relation({self.name})"

    def children(self) -> List[Node]:
        return []


@dataclass
class Select(Node):
    cond: Node
    child: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Select(cond={self.cond.label()})"

    def children(self) -> List[Node]:
        return [self.child]


@dataclass
class Project(Node):
    attrs: List[Attr]
    child: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        names = ", ".join(a.qualified() for a in self.attrs)
        return f"Project(attrs=[{names}])"

    def children(self) -> List[Node]:
        return [self.child]


@dataclass
class Rename(Node):
    new_name: str
    child: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Rename(to={self.new_name})"

    def children(self) -> List[Node]:
        return [self.child]


@dataclass
class BinOp(Node):
    """Base for the four bare infix operators."""
    left: Node
    right: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return type(self).__name__

    def children(self) -> List[Node]:
        return [self.left, self.right]


@dataclass
class Union(BinOp):
    pass


@dataclass
class Intersect(BinOp):
    pass


@dataclass
class Minus(BinOp):
    pass


@dataclass
class Times(BinOp):
    pass


@dataclass
class Join(Node):
    cond: Node
    left: Node
    right: Node
    pos: Pos = (0, 0)

    def label(self) -> str:
        return f"Join(cond={self.cond.label()})"

    def children(self) -> List[Node]:
        return [self.left, self.right]


# --------------------------------------------------------------------------
# Tree printing
# --------------------------------------------------------------------------

def format_tree(node: Node) -> str:
    """Render an expression tree using box-drawing connectors.

    The root sits flush left; every other node is introduced by a connector.
    `prefix` accumulates the indentation for deeper levels: a child of a
    non-last sibling needs a vertical bar carried down through its whole
    subtree, a child of a last sibling needs blank space.
    """
    lines: List[str] = [node.label()]
    _render_children(node, "", lines)
    return "\n".join(lines)


def _render_children(node: Node, prefix: str, lines: List[str]) -> None:
    kids = node.children()
    for i, kid in enumerate(kids):
        last = (i == len(kids) - 1)
        connector = "└── " if last else "├── "
        lines.append(prefix + connector + kid.label())
        _render_children(kid, prefix + ("    " if last else "│   "), lines)


def tree_signature(node: Node) -> str:
    """Parenthesised one-line form, used by tests to compare tree shapes.

    Independent of whitespace and of source positions, which is what case 2
    needs: `select[x1=3](R)` and `select[ x1 = 3 ](R)` must produce the same
    signature even though every token sits at a different column.
    """
    kids = node.children()
    if not kids:
        return node.label()
    inner = ", ".join(tree_signature(k) for k in kids)
    return f"{node.label()}[{inner}]"
