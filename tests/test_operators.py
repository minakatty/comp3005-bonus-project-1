"""
Required test cases 18 to 25 from Section 7.3, plus edge cases around
qualified names, schema/type/name errors, and load-time checks.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ralang.catalog import parse_catalog            # noqa: E402
from ralang.errors import NameError_, SchemaError, TypeError_  # noqa: E402
from ralang.instrument import Counters               # noqa: E402
from ralang.operators import evaluate, format_relation  # noqa: E402
from ralang.parser import parse_query                # noqa: E402


EMPLOYEES = """
Employees (EID, Name, Age, DID) = {
  E1, John, 32, D1
  E2, Alice, 28, D2
  E3, Bob, 29, D1
}
"""

# Emp/Dept, with a self-referencing MgrID, for the join and self-join cases.
EMP_DEPT = """
Emp (EID, Name, MgrID, DID) = {
  E1, John, E3, D1
  E2, Alice, E3, D2
  E3, Bob, E1, D1
}
Dept (DID, DName) = {
  D1, Engineering
  D2, Sales
}
"""

SETS = """
R (a, b) = {
  1, 2
  3, 4
}
S (a, b) = {
  3, 4
  5, 6
}
T (a, c) = {
  1, 2
}
"""


def run(catalog_source: str, query: str, counters: Counters = None):
    catalog = parse_catalog(catalog_source)
    node = parse_query(query)
    return evaluate(node, catalog, counters if counters is not None else Counters())


class RequiredSemanticsCases(unittest.TestCase):

    def test_case_18_attribute_vs_attribute_comparison(self):
        src = "P (A, B) = {\n1, 1\n1, 2\n2, 2\n}\n"
        rel = run(src, "select[A=B](P)")
        self.assertEqual(sorted(rel.rows), [(1, 1), (2, 2)])

    def test_case_19_qualified_join_keeps_both_did_columns_distinguishable(self):
        rel = run(EMP_DEPT, "Emp join[Emp.DID=Dept.DID] Dept")
        self.assertEqual(rel.schema.names().count("DID"), 2)
        owners = {a.relation for a in rel.schema.attrs if a.name == "DID"}
        self.assertEqual(owners, {"Emp", "Dept"})
        self.assertEqual(len(rel.rows), 3)         # every Emp has a matching Dept

    def test_case_20_self_join_via_rename(self):
        rel = run(EMP_DEPT, "rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp")
        # E1->E3(Bob), E2->E3(Bob), E3->E1(John): 3 employee/manager pairs.
        self.assertEqual(len(rel.rows), 3)

    def test_case_20_without_rename_is_unanswerable(self):
        # Emp times Emp collides on every qualified name (Emp.EID, Emp.Name,
        # ...) before the join condition is ever evaluated -- this is *why*
        # case 20 needs rename, and it's worth having as an explicit test.
        with self.assertRaises(SchemaError):
            run(EMP_DEPT, "Emp join[Emp.MgrID=Emp.EID] Emp")

    def test_case_21_union_of_incompatible_schemas_is_a_schema_error(self):
        with self.assertRaises(SchemaError):
            run(SETS, "R union T")           # T has attribute 'c', not 'b'

    def test_case_22_number_vs_string_comparison_is_a_type_error(self):
        with self.assertRaises(TypeError_):
            run(EMPLOYEES, "select[Age>'30'](Employees)")

    def test_case_23_project_removes_duplicates(self):
        rel = run(EMPLOYEES, "project[DID](Employees)")
        self.assertEqual(sorted(rel.rows), [("D1",), ("D2",)])   # 2, not 3

    def test_case_24_repeated_attribute_in_one_projection_is_an_error(self):
        # Documented choice (README/GRAMMAR.md): rejected, not collapsed.
        with self.assertRaises(SchemaError):
            run(EMPLOYEES, "project[Name, Name](Employees)")

    def test_case_25_empty_result_prints_schema_and_no_rows(self):
        rel = run(EMPLOYEES, "select[Age>999](Employees)")
        self.assertEqual(rel.rows, [])
        out = format_relation(rel)
        self.assertIn("Age", out)
        self.assertIn("(0 tuples)", out)


class SetOperators(unittest.TestCase):

    def test_union_combines_and_dedups(self):
        rel = run(SETS, "R union S")
        self.assertEqual(sorted(rel.rows), [(1, 2), (3, 4), (5, 6)])
        self.assertEqual(rel.rows.count((3, 4)), 1)   # shared row appears once

    def test_intersect(self):
        self.assertEqual(run(SETS, "R intersect S").rows, [(3, 4)])

    def test_minus(self):
        self.assertEqual(run(SETS, "R minus S").rows, [(1, 2)])

    def test_minus_is_not_symmetric(self):
        self.assertEqual(run(SETS, "S minus R").rows, [(5, 6)])


class TimesOperator(unittest.TestCase):

    def test_times_widens_schema_and_qualifies(self):
        rel = run(SETS, "R times T")
        self.assertEqual(len(rel.schema.attrs), 4)
        self.assertEqual(len(rel.rows), 2 * 1)
        self.assertEqual({a.relation for a in rel.schema.attrs}, {"R", "T"})

    def test_times_collision_on_identical_relation_is_an_error(self):
        with self.assertRaises(SchemaError):
            run(SETS, "R times R")


class RenameOperator(unittest.TestCase):

    def test_rename_changes_owner_not_attribute_names(self):
        rel = run(SETS, "rename[Q](R)")
        self.assertEqual(rel.schema.names(), ["a", "b"])
        self.assertTrue(all(a.relation == "Q" for a in rel.schema.attrs))


class NameErrors(unittest.TestCase):

    def test_unknown_relation(self):
        with self.assertRaises(NameError_):
            run(SETS, "Nope")

    def test_unknown_attribute(self):
        with self.assertRaises(NameError_):
            run(SETS, "select[zz=1](R)")

    def test_unqualified_attribute_ambiguous_after_times(self):
        src = "A (x, y) = {\n1, 2\n}\nB (x, z) = {\n1, 3\n}\n"
        with self.assertRaises(NameError_):
            run(src, "select[x=1](A times B)")

    def test_qualifying_resolves_the_same_ambiguity(self):
        src = "A (x, y) = {\n1, 2\n}\nB (x, z) = {\n1, 3\n}\n"
        rel = run(src, "select[A.x=1](A times B)")
        self.assertEqual(len(rel.rows), 1)


class CatalogLoading(unittest.TestCase):

    def test_relation_body_deduplicates_on_load(self):
        catalog = parse_catalog("R (a) = {\n1\n1\n2\n}\n")
        self.assertEqual(sorted(catalog["R"].rows), [(1,), (2,)])

    def test_arity_mismatch_is_a_schema_error(self):
        with self.assertRaises(SchemaError):
            parse_catalog("R (a, b) = {\n1, 2, 3\n}\n")

    def test_mixed_column_types_is_a_schema_error(self):
        with self.assertRaises(SchemaError):
            parse_catalog("R (a) = {\n1\n'x'\n}\n")

    def test_duplicate_relation_name_is_a_schema_error(self):
        with self.assertRaises(SchemaError):
            parse_catalog("R (a) = {\n1\n}\nR (a) = {\n2\n}\n")


class JoinEqualsTimesThenSelect(unittest.TestCase):
    """join[c] is *defined* as times followed by select[c] (Section 4.3).
    It isn't *implemented* that way -- see operators.py's module docstring --
    so this proves the two never quietly disagree."""

    def _check(self, catalog_source, left_query, cond, right_query):
        catalog = parse_catalog(catalog_source)

        join_rel = evaluate(
            parse_query(f"{left_query} join[{cond}] {right_query}"),
            catalog, Counters())
        composed_rel = evaluate(
            parse_query(f"select[{cond}]({left_query} times {right_query})"),
            catalog, Counters())

        self.assertEqual(sorted(join_rel.rows), sorted(composed_rel.rows))
        self.assertEqual(join_rel.schema.names(), composed_rel.schema.names())

    def test_equivalence_on_emp_dept(self):
        self._check(EMP_DEPT, "Emp", "Emp.DID=Dept.DID", "Dept")

    def test_equivalence_on_self_join(self):
        self._check(EMP_DEPT, "rename[E2](Emp)", "Emp.MgrID=E2.EID", "Emp")

    def test_equivalence_with_no_matches(self):
        self._check(SETS, "R", "R.a=T.a and R.b=999", "T")


class Instrumentation(unittest.TestCase):
    """Sanity checks on the Section 8.2 counters, ahead of the full sweep."""

    def test_times_comparisons_is_exactly_n_times_m(self):
        src = "R (a) = {\n1\n2\n3\n}\nS (a) = {\n1\n2\n}\n"
        counters = Counters()
        run(src, "R times S", counters)
        self.assertEqual(counters.comparisons, 3 * 2)

    def test_select_examined_is_exactly_the_input_size(self):
        src = "R (a) = {\n1\n2\n3\n4\n}\n"
        counters = Counters()
        run(src, "select[a>2](R)", counters)
        self.assertEqual(counters.examined, 4)

    def test_join_comparisons_equals_n_times_m(self):
        src = "R (a, b) = {\n1, 10\n2, 20\n}\nS (b, c) = {\n10, 'x'\n20, 'y'\n30, 'z'\n}\n"
        counters = Counters()
        run(src, "R join[R.b=S.b] S", counters)
        self.assertEqual(counters.comparisons, 2 * 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)