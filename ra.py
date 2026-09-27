#!/usr/bin/env python3
"""
Command line front end.

    python ra.py --tree   "project[Name](select[Age>30](Employees))"
    python ra.py --tokens "select[Age>=30](R)"

This is the only place an RAError is caught. Everything below raises; the
boundary renders. That is what keeps a stack trace off the user's screen
without wrapping every internal call in a try block.
"""

import sys

from ralang.ast_nodes import format_tree
from ralang.catalog import parse_catalog_file
from ralang.errors import RAError
from ralang.instrument import Counters
from ralang.operators import evaluate, format_relation
from ralang.parser import parse_query
from ralang.tokenizer import TokType, tokenize


USAGE = """usage:
  python ra.py --tree   "<query>"                      print the parse tree
  python ra.py --tokens "<query>"                      print the token stream
  python ra.py --run    "<query>" --data f1.ra [f2.ra ...]
                                                         run and print the result
"""


def cmd_tree(text: str) -> int:
    print(format_tree(parse_query(text)))
    return 0


def cmd_tokens(text: str) -> int:
    for tok in tokenize(text):
        if tok.type is TokType.EOF:
            continue
        shown = "\\n" if tok.type is TokType.NEWLINE else tok.text
        print(f"  {tok.line}:{tok.col:<4} {tok.type.name:<9} {shown}")
    return 0


def cmd_run(text: str, data_paths) -> int:
    catalog = {}
    for path in data_paths:
        catalog.update(parse_catalog_file(path))
    node = parse_query(text)
    counters = Counters()
    rel = evaluate(node, catalog, counters)
    print(format_relation(rel))
    return 0


def main(argv) -> int:
    if len(argv) < 3 or argv[1] not in ("--tree", "--tokens", "--run"):
        print(USAGE, end="")
        return 2

    text = argv[2]
    try:
        if argv[1] == "--tree":
            return cmd_tree(text)
        if argv[1] == "--tokens":
            return cmd_tokens(text)

        # --run "<query>" --data f1.ra [f2.ra ...]
        if len(argv) < 5 or argv[3] != "--data":
            print(USAGE, end="")
            return 2
        return cmd_run(text, argv[4:])
    except RAError as err:
        print(err.render(text), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
