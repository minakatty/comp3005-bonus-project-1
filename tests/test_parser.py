"""
Required test cases 10 to 17 from Section 7.2.

Run from the repository root:  python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ralang.ast_nodes import format_tree, tree_signature   # noqa: E402
from ralang.errors import SyntaxError_                     # noqa: E402
from ralang.parser import parse_query                      # noqa: E402


def sig(source):
    return tree_signature(parse_query(source))


def cond_label(source):
    """The inline condition label of the outermost Select."""
    return parse_query(source).cond.label()


class Precedence(unittest.TestCase):

    def test_case_10_union_minus_groups_left(self):
        # GRAMMAR.md 2.1: union and minus share a level and associate left,
        # so this is (A union B) minus C.
        self.assertEqual(
            sig("A union B minus C"),
            "Minus[Union[Relation(A), Relation(B)], Relation(C)]")

    def test_case_10_printed_tree_matches_the_document(self):
        self.assertEqual(format_tree(parse_query("A union B minus C")), "\n".join([
            "Minus",
            "├── Union",
            "│   ├── Relation(A)",
            "│   └── Relation(B)",
            "└── Relation(C)",
        ]))

    def test_case_11_minus_is_left_associative(self):
        self.assertEqual(
            sig("A minus B minus C"),
            "Minus[Minus[Relation(A), Relation(B)], Relation(C)]")

    def test_case_12_not_binds_tighter_than_and_tighter_than_or(self):
        self.assertEqual(
            cond_label("select[not (a=1 and b=2) or c>3](R)"),
            "Or(Not(And(Eq(Attr(a), Num(1)), Eq(Attr(b), Num(2)))), "
            "Gt(Attr(c), Num(3)))")

    def test_case_13_and_binds_tighter_than_or(self):
        self.assertEqual(
            cond_label("select[a=1 and b=2 or c=3](R)"),
            "Or(And(Eq(Attr(a), Num(1)), Eq(Attr(b), Num(2))), "
            "Eq(Attr(c), Num(3)))")

    def test_case_14_three_levels_of_nesting(self):
        self.assertEqual(
            sig("project[Name](select[Age>30](select[DID='D1'](Employees)))"),
            "Project(attrs=[Name])["
            "Select(cond=Gt(Attr(Age), Num(30)))["
            "Select(cond=Eq(Attr(DID), Str('D1')))[Relation(Employees)]]]")

    def test_case_15_parentheses_override_precedence(self):
        self.assertEqual(
            sig("(A union B) minus (C intersect D)"),
            "Minus[Union[Relation(A), Relation(B)], "
            "Intersect[Relation(C), Relation(D)]]")

    def test_case_16_missing_paren_names_the_opener(self):
        with self.assertRaises(SyntaxError_) as ctx:
            parse_query("select[Age>30](R")
        err = ctx.exception
        self.assertIn("never closed", err.message)
        self.assertEqual(err.col, 15)          # the '(' before R

    def test_case_17_empty_attribute_list(self):
        with self.assertRaises(SyntaxError_) as ctx:
            parse_query("project[](R)")
        self.assertIn("empty attribute list", ctx.exception.message)


class TokenizerParserAgreement(unittest.TestCase):

    def test_cases_1_and_2_produce_identical_trees(self):
        self.assertEqual(sig("select[x1=3](R)"), sig("select[ x1 = 3 ](R)"))

    def test_case_8_keyword_as_attribute_reaches_the_ast(self):
        self.assertEqual(cond_label("select[union=3](R)"),
                         "Eq(Attr(union), Num(3))")


class BinaryOperatorPrecedence(unittest.TestCase):

    def test_times_binds_tighter_than_union(self):
        self.assertEqual(
            sig("A union B times C"),
            "Union[Relation(A), Times[Relation(B), Relation(C)]]")

    def test_intersect_binds_tighter_than_minus(self):
        self.assertEqual(
            sig("A minus B intersect C"),
            "Minus[Relation(A), Intersect[Relation(B), Relation(C)]]")

    def test_join_is_infix_with_a_bracketed_condition(self):
        self.assertEqual(
            sig("Emp join[Emp.DID=Dept.DID] Dept"),
            "Join(cond=Eq(Attr(Emp.DID), Attr(Dept.DID)))"
            "[Relation(Emp), Relation(Dept)]")

    def test_case_20_self_join_shape(self):
        self.assertEqual(
            sig("rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp"),
            "Join(cond=Eq(Attr(Emp.MgrID), Attr(E2.EID)))"
            "[Rename(to=E2)[Relation(Emp)], Relation(Emp)]")


class SoftKeywordEdges(unittest.TestCase):
    """Where I expect the soft-keyword rule to be under most strain."""

    def test_not_as_an_attribute_name(self):
        # 'not' followed by a comparison operator cannot be prefix negation.
        self.assertEqual(cond_label("select[not=1](R)"),
                         "Eq(Attr(not), Num(1))")

    def test_and_as_an_attribute_name_on_the_right(self):
        self.assertEqual(cond_label("select[a=1 and and=2](R)"),
                         "And(Eq(Attr(a), Num(1)), Eq(Attr(and), Num(2)))")

    def test_relation_named_select_is_still_the_operator(self):
        # Documented consequence: in Primary position the operator test wins.
        with self.assertRaises(SyntaxError_):
            parse_query("select union B")


class SyntaxErrors(unittest.TestCase):

    def test_missing_right_operand(self):
        with self.assertRaises(SyntaxError_):
            parse_query("A union")

    def test_trailing_junk_after_complete_query(self):
        with self.assertRaises(SyntaxError_) as ctx:
            parse_query("A B")
        self.assertIn("after a complete query", ctx.exception.message)

    def test_missing_comparison_operator(self):
        with self.assertRaises(SyntaxError_) as ctx:
            parse_query("select[Age](R)")
        self.assertIn("comparison operator", ctx.exception.message)

    def test_unclosed_bracket_blames_the_bracket(self):
        with self.assertRaises(SyntaxError_) as ctx:
            parse_query("select[Age>30(R)")
        self.assertIn("never closed", ctx.exception.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
