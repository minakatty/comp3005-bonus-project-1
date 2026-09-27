"""
Recursive descent parser.

There is one method per non-terminal in GRAMMAR.md, named after it. Read the
two side by side; if they ever disagree, the grammar document is the spec and
this file is the bug.

    Query         ::= UnionExpr                        _query
    UnionExpr     ::= IntersectExpr { (union|minus) IntersectExpr }   _union_expr
    IntersectExpr ::= ProductExpr { intersect ProductExpr }           _intersect_expr
    ProductExpr   ::= Primary { times Primary | join[C] Primary }     _product_expr
    Primary       ::= select[C](Q) | project[A](Q) | rename[I](Q)
                    | "(" Q ")" | IDENT                               _primary

    Condition     ::= OrCond                           _condition
    OrCond        ::= AndCond { or AndCond }           _or_cond
    AndCond       ::= NotCond { and NotCond }          _and_cond
    NotCond       ::= not NotCond | CondPrimary        _not_cond
    CondPrimary   ::= "(" Condition ")" | Comparison   _cond_primary
    Comparison    ::= Operand CompOp Operand           _comparison
    Operand       ::= NUMBER | STRING | AttrRef        _operand

Every `{ ... }` loop is written as a `while` that folds left, which is both how
left recursion is avoided and how left associativity is obtained.
"""

from typing import List, Optional

from . import ast_nodes as ast
from .errors import SyntaxError_
from .tokenizer import Token, TokType, tokenize

# Comparison operator token types, in one place so _comparison and the
# `not`-as-attribute lookahead in _not_cond cannot drift apart.
COMPARE_OPS = {TokType.EQ, TokType.NE, TokType.LT,
               TokType.LE, TokType.GT, TokType.GE}


class Parser:

    def __init__(self, tokens: List[Token], source: str = ""):
        self.toks = tokens
        self.source = source
        self.i = 0
        # Newlines only matter inside a relation body (see GRAMMAR.md 1.1).
        # While parsing a query they are pure whitespace.
        self.nl_significant = False

    # -- token-level helpers ------------------------------------------------

    def _peek(self, ahead: int = 0) -> Token:
        idx, seen = self.i, 0
        while idx < len(self.toks):
            tok = self.toks[idx]
            if tok.type is TokType.NEWLINE and not self.nl_significant:
                idx += 1
                continue
            if seen == ahead:
                return tok
            seen += 1
            idx += 1
        return self.toks[-1]                       # EOF token

    def _advance(self) -> Token:
        tok = self._peek()
        while self.i < len(self.toks) and self.toks[self.i] is not tok:
            self.i += 1
        if self.toks[self.i].type is not TokType.EOF:
            self.i += 1
        return tok

    def _at(self, type_: TokType) -> bool:
        return self._peek().type is type_

    def _at_word(self, word: str, ahead: int = 0) -> bool:
        """True if the token is the IDENT spelled `word`.

        This is the whole of the soft-keyword mechanism from GRAMMAR.md 5.3.
        The scanner never reserved anything, so 'is this an operator?' is a
        question only the parser can answer, and it answers it by position:
        this is only ever called where an operator is grammatically possible.
        """
        tok = self._peek(ahead)
        return tok.type is TokType.IDENT and tok.value == word

    def _expect(self, type_: TokType, what: str) -> Token:
        if not self._at(type_):
            got = self._describe(self._peek())
            raise self._error(f"expected {what}, found {got}")
        return self._advance()

    def _expect_close(self, type_: TokType, opener: Token, what: str) -> Token:
        """Close a bracket, blaming the *opening* token when it never closes.

        Case 16 (`select[Age>30](R`) wants the missing parenthesis named. The
        cursor is at end of input by then, which is a useless place to point,
        so the error carries the position of the '(' that was left open.
        """
        if not self._at(type_):
            raise SyntaxError_(
                f"unbalanced {what}: '{opener.text}' opened here is never closed",
                opener.line, opener.col, opener.offset)
        return self._advance()

    @staticmethod
    def _describe(tok: Token) -> str:
        if tok.type is TokType.EOF:
            return "end of input"
        if tok.type is TokType.NEWLINE:
            return "end of line"
        if tok.type is TokType.STRING:
            return f"string '{tok.value}'"
        return f"'{tok.text}'"

    def _error(self, message: str) -> SyntaxError_:
        tok = self._peek()
        return SyntaxError_(message, tok.line, tok.col, tok.offset)

    # ======================================================================
    # Expressions
    # ======================================================================

    def parse_query(self) -> ast.Node:
        node = self._union_expr()
        if not self._at(TokType.EOF):
            raise self._error(
                f"unexpected {self._describe(self._peek())} after a complete query")
        return node

    def _union_expr(self) -> ast.Node:
        # UnionExpr ::= IntersectExpr { ( "union" | "minus" ) IntersectExpr }
        node = self._intersect_expr()
        while self._at_word("union") or self._at_word("minus"):
            op = self._advance()
            right = self._intersect_expr()
            cls = ast.Union if op.value == "union" else ast.Minus
            # Folding into `node` on each iteration is what makes this left
            # associative: (A union B) minus C, never A union (B minus C).
            node = cls(node, right, (op.line, op.col))
        return node

    def _intersect_expr(self) -> ast.Node:
        node = self._product_expr()
        while self._at_word("intersect"):
            op = self._advance()
            node = ast.Intersect(node, self._product_expr(), (op.line, op.col))
        return node

    def _product_expr(self) -> ast.Node:
        node = self._primary()
        while self._at_word("times") or self._at_word("join"):
            op = self._advance()
            if op.value == "times":
                node = ast.Times(node, self._primary(), (op.line, op.col))
            else:
                lb = self._expect(TokType.LBRACKET, "'[' after 'join'")
                cond = self._condition()
                self._expect_close(TokType.RBRACKET, lb, "bracket")
                node = ast.Join(cond, node, self._primary(), (op.line, op.col))
        return node

    def _primary(self) -> ast.Node:
        tok = self._peek()

        if tok.type is TokType.IDENT:
            if tok.value == "select":
                return self._select()
            if tok.value == "project":
                return self._project()
            if tok.value == "rename":
                return self._rename()
            self._advance()
            return ast.Relation(tok.value, (tok.line, tok.col))

        if tok.type is TokType.LPAREN:
            opener = self._advance()
            node = self._union_expr()
            self._expect_close(TokType.RPAREN, opener, "parenthesis")
            return node

        raise self._error(
            f"expected a relation name or an operator, found {self._describe(tok)}")

    def _select(self) -> ast.Node:
        kw = self._advance()
        lb = self._expect(TokType.LBRACKET, "'[' after 'select'")
        cond = self._condition()
        self._expect_close(TokType.RBRACKET, lb, "bracket")
        lp = self._expect(TokType.LPAREN, "'(' after select[...]")
        child = self._union_expr()
        self._expect_close(TokType.RPAREN, lp, "parenthesis")
        return ast.Select(cond, child, (kw.line, kw.col))

    def _project(self) -> ast.Node:
        kw = self._advance()
        lb = self._expect(TokType.LBRACKET, "'[' after 'project'")
        attrs = self._attr_list()
        self._expect_close(TokType.RBRACKET, lb, "bracket")
        lp = self._expect(TokType.LPAREN, "'(' after project[...]")
        child = self._union_expr()
        self._expect_close(TokType.RPAREN, lp, "parenthesis")
        return ast.Project(attrs, child, (kw.line, kw.col))

    def _rename(self) -> ast.Node:
        kw = self._advance()
        lb = self._expect(TokType.LBRACKET, "'[' after 'rename'")
        name = self._expect(TokType.IDENT, "a new relation name")
        self._expect_close(TokType.RBRACKET, lb, "bracket")
        lp = self._expect(TokType.LPAREN, "'(' after rename[...]")
        child = self._union_expr()
        self._expect_close(TokType.RPAREN, lp, "parenthesis")
        return ast.Rename(name.value, child, (kw.line, kw.col))

    def _attr_list(self) -> List[ast.Attr]:
        # AttrList ::= AttrRef { "," AttrRef }  -- one or more, by construction.
        # This is why case 17, project[](R), is a syntax error: there is simply
        # no derivation for an empty list, so no separate emptiness check exists.
        if self._at(TokType.RBRACKET):
            raise self._error(
                "an empty attribute list is not a valid projection; "
                "project[...] needs at least one attribute")
        attrs = [self._attr_ref()]
        while self._at(TokType.COMMA):
            self._advance()
            attrs.append(self._attr_ref())
        return attrs

    def _attr_ref(self) -> ast.Attr:
        first = self._expect(TokType.IDENT, "an attribute name")
        if self._at(TokType.DOT):
            self._advance()
            second = self._expect(TokType.IDENT, "an attribute name after '.'")
            return ast.Attr(first.value, second.value, (first.line, first.col))
        return ast.Attr(None, first.value, (first.line, first.col))

    # ======================================================================
    # Conditions
    # ======================================================================

    def _condition(self) -> ast.Node:
        return self._or_cond()

    def _or_cond(self) -> ast.Node:
        node = self._and_cond()
        while self._at_word("or"):
            op = self._advance()
            node = ast.Or(node, self._and_cond(), (op.line, op.col))
        return node

    def _and_cond(self) -> ast.Node:
        node = self._not_cond()
        while self._at_word("and"):
            op = self._advance()
            node = ast.And(node, self._not_cond(), (op.line, op.col))
        return node

    def _not_cond(self) -> ast.Node:
        # NotCond ::= "not" NotCond | CondPrimary
        #
        # Right-recursive, which is safe for recursive descent because 'not' is
        # consumed *before* the recursive call, so the input always shrinks.
        #
        # The lookahead below is the one place the soft-keyword rule needs help.
        # 'and' and 'or' only ever appear where the loops above are looking for
        # an operator, so an attribute spelled `and` is unambiguous. But 'not'
        # is a prefix operator, so it sits exactly where an operand starts. If
        # the next token is a comparison operator then `not` cannot be a prefix
        # operator (nothing can follow it), so it must be an attribute name --
        # which keeps select[not=1](R) working.
        if self._at_word("not") and self._peek(1).type not in COMPARE_OPS:
            op = self._advance()
            return ast.Not(self._not_cond(), (op.line, op.col))
        return self._cond_primary()

    def _cond_primary(self) -> ast.Node:
        if self._at(TokType.LPAREN):
            opener = self._advance()
            node = self._condition()
            self._expect_close(TokType.RPAREN, opener, "parenthesis")
            return node
        return self._comparison()

    def _comparison(self) -> ast.Node:
        left = self._operand()
        tok = self._peek()
        if tok.type not in COMPARE_OPS:
            raise self._error(
                f"expected a comparison operator (=, !=, <, <=, >, >=), "
                f"found {self._describe(tok)}")
        self._advance()
        right = self._operand()
        return ast.Compare(tok.type.name, left, right, (tok.line, tok.col))

    def _operand(self) -> ast.Node:
        tok = self._peek()
        if tok.type is TokType.NUMBER:
            self._advance()
            return ast.Num(tok.value, (tok.line, tok.col))
        if tok.type is TokType.STRING:
            self._advance()
            return ast.Str(tok.value, (tok.line, tok.col))
        if tok.type is TokType.IDENT:
            # Any IDENT here is an attribute, whatever it spells. This is case 8.
            return self._attr_ref()
        raise self._error(
            f"expected a number, a string or an attribute name, "
            f"found {self._describe(tok)}")


def parse_query(source: str) -> ast.Node:
    """Tokenize then parse a single query. Raises RAError subclasses only."""
    return Parser(tokenize(source), source).parse_query()
