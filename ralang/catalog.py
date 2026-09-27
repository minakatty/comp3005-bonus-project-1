"""
Parses relation-definition files (Section 4.1) into a name -> Relation map.

    Definition   ::= IDENT "(" AttrDeclList ")" "=" "{" { TupleLine } "}"
    AttrDeclList ::= IDENT { "," IDENT }
    TupleLine    ::= Value { "," Value } NEWLINE
    Value        ::= NUMBER | STRING

This is a second, small recursive-descent parser, separate from parser.py,
because the query grammar and the definition-file grammar are genuinely
different languages that happen to share a tokenizer. Reusing parser.py's
Parser class here would mean bolting a second, unrelated grammar onto a class
whose every method name is supposed to correspond to a Query non-terminal --
that seemed like the wrong kind of code reuse, so this is its own class over
the same Token stream instead.

Unlike query parsing, newlines are significant here: they are what ends a
TupleLine, which is how case-style arity errors ("this tuple has the wrong
number of values") get detected instead of silently reflowing across lines.
"""

from typing import Dict, List, Tuple

from .errors import SchemaError, SyntaxError_
from .relation import Relation, Row, dedup
from .schema import Attribute, ColType, Schema
from .tokenizer import Token, TokType, tokenize


class _DefParser:

    def __init__(self, tokens: List[Token]):
        self.toks = tokens
        self.i = 0

    def _peek(self, ahead: int = 0) -> Token:
        idx = self.i + ahead
        return self.toks[idx] if idx < len(self.toks) else self.toks[-1]

    def _advance(self) -> Token:
        tok = self.toks[self.i]
        if tok.type is not TokType.EOF:
            self.i += 1
        return tok

    def _at(self, t: TokType) -> bool:
        return self._peek().type is t

    def _skip_newlines(self) -> None:
        while self._at(TokType.NEWLINE):
            self._advance()

    def _expect(self, t: TokType, what: str) -> Token:
        if not self._at(t):
            tok = self._peek()
            shown = tok.text if tok.type is not TokType.EOF else "end of input"
            raise SyntaxError_(f"expected {what}, found '{shown}'",
                               tok.line, tok.col, tok.offset)
        return self._advance()

    # -- top level ------------------------------------------------------

    def parse_catalog(self) -> Dict[str, Relation]:
        catalog: Dict[str, Relation] = {}
        self._skip_newlines()
        while not self._at(TokType.EOF):
            name_tok, rel = self._definition()
            if name_tok.value in catalog:
                raise SchemaError(
                    f"relation '{name_tok.value}' is defined more than once",
                    name_tok.line, name_tok.col, name_tok.offset)
            catalog[name_tok.value] = rel
            self._skip_newlines()
        return catalog

    def _definition(self) -> Tuple[Token, Relation]:
        name_tok = self._expect(TokType.IDENT, "a relation name")
        self._expect(TokType.LPAREN, "'(' after the relation name")

        attr_names = [self._expect(TokType.IDENT, "an attribute name").value]
        while self._at(TokType.COMMA):
            self._advance()
            attr_names.append(self._expect(TokType.IDENT, "an attribute name").value)

        self._expect(TokType.RPAREN, "')' to close the attribute list")
        self._expect(TokType.EQ, "'=' after the attribute list")
        self._expect(TokType.LBRACE, "'{' to start the relation body")
        self._skip_newlines()

        rows: List[Row] = []
        while not self._at(TokType.RBRACE):
            rows.append(self._tuple_line(name_tok.value, len(attr_names)))
            self._skip_newlines()
        self._expect(TokType.RBRACE, "'}' to close the relation body")

        rows = dedup(rows)                              # 4.1: "a relation is a set"
        types = self._infer_types(name_tok.value, attr_names, rows)
        attrs = [Attribute(name_tok.value, a) for a in attr_names]
        return name_tok, Relation(Schema(attrs, types), rows)

    def _tuple_line(self, rel_name: str, arity: int) -> Row:
        start = self._peek()
        values = [self._value()]
        while self._at(TokType.COMMA):
            self._advance()
            values.append(self._value())

        if not self._at(TokType.NEWLINE) and not self._at(TokType.RBRACE):
            tok = self._peek()
            raise SyntaxError_(f"unexpected '{tok.text}' in a tuple line "
                               f"of relation '{rel_name}'",
                               tok.line, tok.col, tok.offset)
        if self._at(TokType.NEWLINE):
            self._advance()

        if len(values) != arity:
            raise SchemaError(
                f"relation '{rel_name}' declares {arity} attribute(s) but "
                f"this tuple has {len(values)} value(s)",
                start.line, start.col, start.offset)
        return tuple(values)

    def _value(self):
        tok = self._peek()
        if tok.type in (TokType.NUMBER, TokType.STRING):
            self._advance()
            return tok.value
        if tok.type is TokType.IDENT:
            # A bare, unquoted string -- 'John' rather than "'John'".
            self._advance()
            return tok.value
        raise SyntaxError_(f"expected a value, found '{tok.text}'",
                           tok.line, tok.col, tok.offset)

    @staticmethod
    def _infer_types(rel_name: str, attr_names: List[str],
                     rows: List[Row]) -> List[ColType]:
        """One type per column, decided once at load time.

        Every value in a column must be the same kind (see schema.py's
        module docstring for why). An empty relation has no values to look
        at; STRING is chosen arbitrarily in that case and never observed,
        since no comparison can happen against a column with no rows behind
        it in the only two test relations that matter here.
        """
        types = []
        for i, attr_name in enumerate(attr_names):
            if not rows:
                types.append(ColType.STRING)          # arbitrary; never observed
                continue
            kinds = {type(row[i]) for row in rows}
            if kinds <= {int, float}:
                types.append(ColType.NUMBER)
            elif kinds <= {str}:
                types.append(ColType.STRING)
            else:
                raise SchemaError(
                    f"column '{attr_name}' of relation '{rel_name}' mixes "
                    f"numbers and strings; every value in a column must be "
                    f"the same kind")
        return types


def parse_catalog(source: str) -> Dict[str, Relation]:
    return _DefParser(tokenize(source)).parse_catalog()


def parse_catalog_file(path: str) -> Dict[str, Relation]:
    with open(path, "r", encoding="utf-8") as f:
        return parse_catalog(f.read())
