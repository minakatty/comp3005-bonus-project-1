"""
The five error categories required by Section 6.3.

These are exceptions internally, because raising is how you abandon a half-built
parse from deep inside recursive descent. But nothing above `ra.py` ever sees a
traceback: the CLI catches RAError once, calls render(), and exits non-zero.
"""

from typing import Optional


class RAError(Exception):
    kind = "Error"

    def __init__(self, message: str,
                 line: Optional[int] = None,
                 col: Optional[int] = None,
                 offset: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.offset = offset

    def render(self, source: str = "") -> str:
        """Human-readable message, with a caret under the offending column."""
        if self.line is None:
            return f"{self.kind}: {self.message}"

        out = f"{self.kind} at line {self.line}, column {self.col}: {self.message}"
        lines = source.splitlines()
        if 0 < self.line <= len(lines):
            out += "\n  " + lines[self.line - 1]
            out += "\n  " + " " * (self.col - 1) + "^"
        return out


class LexicalError(RAError):
    """Unterminated string, stray character."""
    kind = "Lexical error"


class SyntaxError_(RAError):
    """Unbalanced parentheses, missing operand, empty attribute list."""
    kind = "Syntax error"


class NameError_(RAError):
    """Unknown relation or unknown attribute."""
    kind = "Name error"


class SchemaError(RAError):
    """Union of incompatible relations, colliding qualified names."""
    kind = "Schema error"


class TypeError_(RAError):
    """Comparing a number to a string."""
    kind = "Type error"
