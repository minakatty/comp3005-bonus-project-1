"""
Section 8.2: "Add a counter that increments once for every pair of tuples
your join compares, and once for every tuple your selection examines. Count
these. Do not estimate them."

Two separate counters, because they measure two different things that only
coincide for a join:

  comparisons -- incremented once per pair of tuples the cross product in
                 `times` generates. This is where a join's nested loop
                 actually lives (join is defined as times-then-select, and
                 that is implemented literally, not just described that
                 way), so this counter is exactly n * m for a full cross
                 product between relations of size n and m.

  examined    -- incremented once per tuple a `select` node looks at. For a
                 bare select[cond](R), that is |R|. Because a join's select
                 phase runs over the times output, examined also reaches
                 n * m during a join -- not because it is the same counter,
                 but because that is what the definition in Section 4.3
                 implies.

Keeping them separate is what lets Section 8.4 Q3 ask for select and project
curves independently of the join curve using the same instrumentation.
"""

from dataclasses import dataclass


@dataclass
class Counters:
    comparisons: int = 0
    examined: int = 0

    def reset(self) -> None:
        self.comparisons = 0
        self.examined = 0
