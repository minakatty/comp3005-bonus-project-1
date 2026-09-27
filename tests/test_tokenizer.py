import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""
Required test cases 1 to 9 from Section 7.1 of the spec.

Run with:  python -m unittest test_tokenizer -v
"""

import unittest

from ralang.tokenizer import TokType, LexicalError, tokenize


def shape(source):
    """Token stream as (type, value) pairs, dropping positions and EOF.

    Positions are dropped deliberately: case 2 requires that whitespace does
    not change the token stream, and positions necessarily do change.
    """
    return [(t.type, t.value) for t in tokenize(source)
            if t.type is not TokType.EOF]


class TokenizerCases(unittest.TestCase):

    def test_case_01_no_whitespace_at_all(self):
        # The scanner, not a split on spaces, separates x1, = and 3.
        self.assertEqual(shape("select[x1=3](R)"), [
            (TokType.IDENT, "select"),
            (TokType.LBRACKET, None),
            (TokType.IDENT, "x1"),
            (TokType.EQ, None),
            (TokType.NUMBER, 3),
            (TokType.RBRACKET, None),
            (TokType.LPAREN, None),
            (TokType.IDENT, "R"),
            (TokType.RPAREN, None),
        ])

    def test_case_02_whitespace_is_irrelevant(self):
        self.assertEqual(shape("select[ x1 = 3 ](R)"),
                         shape("select[x1=3](R)"))

    def test_case_03_maximal_munch_produces_ge(self):
        self.assertIn((TokType.GE, None), shape("select[Age>=30](R)"))
        self.assertNotIn((TokType.GT, None), shape("select[Age>=30](R)"))

    def test_case_04_gt_then_negative_number(self):
        # Maximal munch must not invent a '>-' operator.
        toks = shape("select[Age>-30](R)")
        self.assertIn((TokType.GT, None), toks)
        self.assertIn((TokType.NUMBER, -30), toks)

    def test_case_05_paren_inside_string(self):
        toks = shape("select[Name='Bob)'](R)")
        self.assertIn((TokType.STRING, "Bob)"), toks)
        # Exactly two real parens: the ones wrapping R.
        self.assertEqual(sum(1 for t, _ in toks if t is TokType.LPAREN), 1)
        self.assertEqual(sum(1 for t, _ in toks if t is TokType.RPAREN), 1)

    def test_case_06_comma_inside_string(self):
        toks = shape("select[Name='a,b'](R)")
        self.assertIn((TokType.STRING, "a,b"), toks)
        self.assertNotIn((TokType.COMMA, None), toks)

    def test_case_07_doubled_quote_is_one_quote(self):
        self.assertIn((TokType.STRING, "O'Brien"),
                      shape("select[Name='O''Brien'](R)"))

    def test_case_08_keyword_spelled_as_attribute(self):
        # No word is reserved by the scanner; 'union' stays an IDENT.
        self.assertIn((TokType.IDENT, "union"), shape("select[union=3](R)"))

    def test_case_09_unterminated_string_is_positioned(self):
        with self.assertRaises(LexicalError) as ctx:
            tokenize("select[Name='Bob](R)")
        err = ctx.exception
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 13)          # the opening quote
        self.assertIn("unterminated", err.message)


class ExtraTokenizerChecks(unittest.TestCase):
    """Beyond the required list — these are where I expect to break it."""

    def test_le_and_ne(self):
        self.assertIn((TokType.LE, None), shape("select[a<=1](R)"))
        self.assertIn((TokType.NE, None), shape("select[a!=1](R)"))

    def test_bare_bang_is_a_lexical_error(self):
        with self.assertRaises(LexicalError):
            tokenize("select[a!1](R)")

    def test_qualified_name_keeps_the_dot(self):
        toks = shape("Emp.DID")
        self.assertEqual(toks, [
            (TokType.IDENT, "Emp"),
            (TokType.DOT, None),
            (TokType.IDENT, "DID"),
        ])

    def test_float_versus_dot_separator(self):
        self.assertIn((TokType.NUMBER, 3.5), shape("select[a=3.5](R)"))

    def test_comment_line_does_not_swallow_its_newline(self):
        toks = shape("// note\nE1, John\n")
        self.assertEqual(toks[0][0], TokType.NEWLINE)

    def test_newlines_are_emitted_in_a_relation_body(self):
        src = "R (a, b) = {\n1, 2\n3, 4\n}"
        self.assertEqual(
            sum(1 for t, _ in shape(src) if t is TokType.NEWLINE), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
