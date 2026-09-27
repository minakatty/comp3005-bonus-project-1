"""
Hand-written tokenizer for the relational algebra engine.

Implements Section 5 of GRAMMAR.md. No regular expressions anywhere: this is a
character-by-character scanner that reads one character, decides which token is
starting, and consumes characters until that token ends.

Key properties, each tied to a required test case:

  * maximal munch on '>', '<', '!'                        (case 3)
  * '-' followed by a digit starts a NUMBER, so there     (case 4)
    is no invented '>-' operator
  * strings are scanned over the raw character stream, so (cases 5, 6)
    ')' and ',' inside quotes are never punctuation
  * '' inside a string is one literal quote               (case 7)
  * no word is ever reserved; keywords are resolved by    (case 8)
    the parser, by position
  * unterminated strings raise a positioned lexical error (case 9)

Every token carries its offset, line and column, because the error messages
required by Section 6.3 of the spec depend on it.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, List

from .errors import LexicalError, RAError


# --------------------------------------------------------------------------
# Token types
# --------------------------------------------------------------------------

class TokType(Enum):
    IDENT = "IDENT"
    NUMBER = "NUMBER"
    STRING = "STRING"

    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    LBRACE = "{"
    RBRACE = "}"
    COMMA = ","
    DOT = "."

    EQ = "="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="

    NEWLINE = "NEWLINE"
    EOF = "EOF"


# Single-character tokens with no maximal-munch decision to make.
_SIMPLE = {
    "(": TokType.LPAREN,
    ")": TokType.RPAREN,
    "[": TokType.LBRACKET,
    "]": TokType.RBRACKET,
    "{": TokType.LBRACE,
    "}": TokType.RBRACE,
    ",": TokType.COMMA,
    ".": TokType.DOT,
}


@dataclass(frozen=True)
class Token:
    type: TokType
    text: str               # exact source text of the token
    value: Any              # decoded value for NUMBER / STRING, else None
    offset: int             # 0-based character offset
    line: int               # 1-based
    col: int                # 1-based

    def __repr__(self) -> str:
        if self.value is not None:
            return f"{self.type.name}({self.value!r})@{self.line}:{self.col}"
        return f"{self.type.name}@{self.line}:{self.col}"


# --------------------------------------------------------------------------
# The scanner
# --------------------------------------------------------------------------

class Tokenizer:

    def __init__(self, source: str):
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []

    # -- character-level helpers -------------------------------------------

    def _peek(self, ahead: int = 0) -> str:
        """Return the character `ahead` positions from the cursor, or '' at EOF.

        Returning '' rather than raising means every call site can compare
        against a literal without a bounds check first.
        """
        i = self.pos + ahead
        return self.src[i] if i < len(self.src) else ""

    def _advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _mark(self):
        """Snapshot the cursor so a token can record where it began."""
        return self.pos, self.line, self.col

    def _push(self, type_: TokType, mark, value: Any = None) -> None:
        offset, line, col = mark
        self.tokens.append(
            Token(type_, self.src[offset:self.pos], value, offset, line, col)
        )

    # -- main loop ---------------------------------------------------------

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.src):
            ch = self._peek()

            # Newlines are significant: they terminate tuple lines inside a
            # relation body. The parser discards them everywhere else.
            if ch == "\n":
                mark = self._mark()
                self._advance()
                self._push(TokType.NEWLINE, mark)
                continue

            if ch in " \t\r":
                self._advance()
                continue

            # A comment runs to end of line. The newline itself is left in the
            # stream and emitted on the next iteration, so a comment line looks
            # like a blank line to the parser rather than vanishing and gluing
            # two tuple lines together.
            if ch == "/" and self._peek(1) == "/":
                while self.pos < len(self.src) and self._peek() != "\n":
                    self._advance()
                continue

            if ch == "'":
                self._string()
                continue

            # A '-' begins a number only when a digit follows. The language has
            # no arithmetic, so '-' has no other meaning and this is not
            # ambiguous. This is what makes 'Age>-30' scan as GT then -30.
            if ch.isdigit() or (ch == "-" and self._peek(1).isdigit()):
                self._number()
                continue

            if ch.isalpha():
                self._ident()
                continue

            self._operator()

        self.tokens.append(
            Token(TokType.EOF, "", None, self.pos, self.line, self.col)
        )
        return self.tokens

    # -- individual token scanners -----------------------------------------

    def _string(self) -> None:
        """Scan a single-quoted string. '' inside stands for one literal quote."""
        mark = self._mark()
        _, open_line, open_col = mark
        self._advance()                     # consume the opening quote

        chars: List[str] = []
        while True:
            if self.pos >= len(self.src):
                raise LexicalError(
                    "unterminated string literal: end of input reached before "
                    "the closing quote",
                    open_line, open_col, mark[0])

            ch = self._peek()

            if ch == "\n":
                raise LexicalError(
                    "unterminated string literal: end of line reached before "
                    "the closing quote",
                    open_line, open_col, mark[0])

            if ch == "'":
                # Two quotes in a row are an escaped quote, not the end.
                if self._peek(1) == "'":
                    self._advance()
                    self._advance()
                    chars.append("'")
                    continue
                self._advance()             # consume the closing quote
                break

            chars.append(self._advance())

        self._push(TokType.STRING, mark, "".join(chars))

    def _number(self) -> None:
        mark = self._mark()

        if self._peek() == "-":
            self._advance()

        while self._peek().isdigit():
            self._advance()

        # A '.' continues the number only if a digit follows it. Otherwise the
        # '.' is a qualified-name separator and belongs to the next token.
        if self._peek() == "." and self._peek(1).isdigit():
            self._advance()
            while self._peek().isdigit():
                self._advance()

        text = self.src[mark[0]:self.pos]
        value = float(text) if "." in text else int(text)
        self._push(TokType.NUMBER, mark, value)

    def _ident(self) -> None:
        mark = self._mark()
        self._advance()                     # first character: a letter
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()

        # Deliberately NOT checked against a keyword table. See GRAMMAR.md 5.3:
        # words like 'union' stay IDENT, and the parser decides by position
        # whether they are operators or attribute names. This is what makes
        # select[union=3](R) work.
        self._push(TokType.IDENT, mark, self.src[mark[0]:self.pos])

    def _operator(self) -> None:
        """Scan punctuation and comparison operators, with maximal munch.

        Maximal munch means: having read '>', look at the next character before
        deciding. If it is '=', the token is GE and both characters are
        consumed; otherwise the token is GT and the lookahead is left alone.
        Crucially the scanner only extends a token while the extension is
        itself a legal token, which is why '>-' is never produced.
        """
        mark = self._mark()
        ch = self._advance()

        if ch == ">":
            if self._peek() == "=":
                self._advance()
                self._push(TokType.GE, mark)
            else:
                self._push(TokType.GT, mark)
            return

        if ch == "<":
            if self._peek() == "=":
                self._advance()
                self._push(TokType.LE, mark)
            else:
                self._push(TokType.LT, mark)
            return

        if ch == "!":
            if self._peek() == "=":
                self._advance()
                self._push(TokType.NE, mark)
                return
            raise LexicalError(
                "unexpected character '!' (did you mean '!='?)",
                mark[1], mark[2], mark[0])

        if ch == "=":
            # One token for both the comparison operator and the '=' in a
            # relation definition. The parser tells them apart by position.
            self._push(TokType.EQ, mark)
            return

        if ch in _SIMPLE:
            self._push(_SIMPLE[ch], mark)
            return

        raise LexicalError(
            f"unexpected character {ch!r}",
            mark[1], mark[2], mark[0])


def tokenize(source: str) -> List[Token]:
    return Tokenizer(source).tokenize()


# --------------------------------------------------------------------------
# Small CLI, useful for the video and for debugging the parser later
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--tokens":
        text = sys.argv[2]
    elif len(sys.argv) >= 2 and sys.argv[1] != "--tokens":
        text = sys.argv[1]
    else:
        print('usage: python -m ralang.tokenizer --tokens "select[Age>=30](R)"')
        sys.exit(2)

    try:
        for tok in tokenize(text):
            if tok.type is TokType.EOF:
                continue
            shown = "\\n" if tok.type is TokType.NEWLINE else tok.text
            label = f"{tok.line}:{tok.col}"
            print(f"  {label:>8}  {tok.type.name:<8}  {shown}")
    except RAError as err:
        print(err.render(text))
        sys.exit(1)
