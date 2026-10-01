\# GRAMMAR.md



Grammar for the relational algebra engine. Written before parser







\---



\## Notation



EBNF conventions used throughout:



| Form | Meaning |

|---|---|

| `"x"` | terminal (literal text ) |

| `UPPER` | terminal produced by the scanner (token class) |

| `Lower` | non-terminal | 

| `{ X }` | zero or more repetitions of X | 

| `\[ X ]` | optional X |  

| `X \\| Y` | alternation |  



Token classes produced by the scanner: `IDENT`, `NUMBER`, `STRING`, `NEWLINE`, plus the punctuation and operator literals written in quotes below.



\---



\## 1. The grammar



\### 1.1 Top level



```ebnf

Program      ::= { Definition | Query }



Definition   ::= IDENT "(" AttrDeclList ")" "=" "{" { TupleLine } "}"



AttrDeclList ::= IDENT { "," IDENT }



TupleLine    ::= Value { "," Value } NEWLINE



Value        ::= NUMBER | STRING

```



Why `NEWLINE` is a token. The spec says every tuple line carries exactly as many  values as the relation has attributes. To report an arity mismatch I need to know where a tuple ends. Without line boundaries, a body like



```

E1, John, 32

D1, E2, Alice, 28, D2

```



would silently repartition into two well formed tuples of the right width and I would never detect the error. So the scanner emits `NEWLINE` tokens, and the parser suppresses them everywhere except inside a relation body, where they terminate a tuple



\###  1.2 Query expressions — stratified for precedence



```ebnf

Query        ::= UnionExpr



UnionExpr    ::= IntersectExpr { ( "union" | "minus" ) IntersectExpr }



IntersectExpr::= ProductExpr { "intersect" ProductExpr }



ProductExpr  ::= Primary { ( "times" Primary

&#x20;                          | "join" "\[" Condition "]" Primary ) }



Primary      ::= "select"  "\[" Condition "]" "(" Query ")"

&#x20;              | "project" "\[" AttrList  "]" "(" Query ")"

&#x20;              | "rename"  "\[" IDENT     "]" "(" Query ")"

&#x20;              | "(" Query ")"

&#x20;              | IDENT



AttrList     ::= AttrRef { "," AttrRef }

```



`AttrList` is `{ AttrRef ... }` with \*\*one or more\*\* elements `project\[](R)` case 17 has no derivation, so it is a syntax error by construction rather than by a check bolted on afterwards



\### 1.3 Conditions —  stratified the same way



```ebnf

Condition    ::= OrCond

OrCond       ::= AndCond { "or" AndCond }



AndCond      ::= NotCond { "and" NotCond }



NotCond      ::= "not" NotCond

&#x20;              | CondPrimary

CondPrimary  ::= "(" Condition ")"

&#x20;              | Comparison



Comparison   ::= Operand CompOp Operand



CompOp       ::= "=" | "!=" | "<" | "<=" | ">" | ">="



Operand      ::= NUMBER | STRING | AttrRef



AttrRef      ::= IDENT \[ "." IDENT ]

```

`Comparison` takes an `Operand` on \*\*both\*\* sides, which is what makes case 18 (`select\[A=B](R)`, two attributes compared to each other) fall out of the grammar rather than needing a special case



\###  1.4 Lexical grammar



```ebnf

IDENT        ::= Letter { Letter | Digit | "\_" }

NUMBER       ::= \[ "-" ] Digit { Digit } \[ "." Digit { Digit } ]

STRING       ::= "'" { AnyCharExceptQuote | "''" } "'"

Comment      ::= "//" { AnyCharExceptNewline } NEWLINE

```





\---



\## 2.00 Precedence \& associativity



\###   2.1 Query operators



| Level | Operators | Associativity | Enforcing rule |

|---|---|---|---|



| 1 (tightest) | `select\[]`, `project\[]`, `rename\[]`, `( )`, relation name | — (primary) | `Primary` |

| 2 | `times`, `join\[]` | left | `ProductExpr` |

| 3 | `intersect` | left | `IntersectExpr` |

| 4 (loosest) | `union`, `minus` | left | `UnionExpr` |





`union` and `minus` sit at the \*\*same\*\* level, so `A union B minus C` groups strictly left to right: `(A union B) minus C`



\###  2.02 Condition operators



| Level | Operator | Associativity | Enforcing rule |

|---|---|---|---|

| 1 (tightest) | comparison, `( )` | — | `CondPrimary` |

| 2 | `not` | right (prefix) | `NotCond` |

| 3 | `and` | left | `AndCond` |

| 4 (loosest) | `or` | left | `OrCond` |



This gives case 12 and case 13 directly: `not (a=1 and b=2) or c>3` parses as `(not (a=1 and b=2)) or (c>3)`, \& `a=1 and b=2 or c=3` parses as `(a=1 and b=2) or (c=3)`



\### 2.03 How the stratification encodes both of the facts



Two separate mechanisms are at work and it is worth being able to say which is which:



\- Precedence comes from the layering, Each rule can only descend to the level below it, so a tighter-binding operator is always further down the tree and therefore evaluated first.

\- Associativity comes from the \*shape of the repetition\*. `A { op B }` is a loop, and folding the loop results left-to-right as I go produces left association. Right association would need right recursion instead: `A ::= B op A | B`. `not` is the only right-associative operator here, and it is written with exactly that right-recursive shape.



\---



\## 3.0  Ambiguity demonstration



\### 3.01 The naive grammar



```ebnf

Expr ::= Expr "union" Expr

&#x20;      | Expr "minus" Expr

&#x20;      | "(" Expr ")"

&#x20;      | IDENT

```



\### 3.02 Two parse trees for `A union B minus C`

tree 1 - `(A union B) minus C`



```

&#x20;       Expr(minus)

&#x20;       /         \\

&#x20;  Expr(union)   Expr

&#x20;   /      \\       |

&#x20; Expr    Expr     C

&#x20;  |       |

&#x20;  A       B

```



Tree 2- `A union (B minus C)`



```

&#x20;       Expr(union)

&#x20;       /         \\

&#x20;    Expr      Expr(minus)

&#x20;     |         /      \\

&#x20;     A      Expr     Expr

&#x20;             |        |

&#x20;             B        C

```



Both are valid derivations from the naive grammar, which is the definition of ambiguity: one input string, two distinct parse trees



\###  3.03 a data instance where the trees disagree



```

A (x) = { 1 }

B (x) = { 2 }

C (x) = { 1 }

```



| Tree | Evaluation | Result |

|---|---|---|

| 1 — `(A union B) minus C` | `{1,2} minus {1}` | `{ 2 }` |

| 2 — `A union (B minus C)` | `{1} union {2}` | `{ 1, 2 }` |



Different cardinality, different contents. The ambiguity is not cosmetic it changes the answer, which is why it has to be resolved in the grammar and not left to the parsers' mood



> Note on picking the instance. My first attempt was `A={1}, B={2}, C={2}`, which gives`{1}` both ways and demonstrates nothing. To separate the trees, `C` has to remove something that only the left grouping exposes to it , i.e. an element of `A`. That is the property to reason about not a lucky guess



\### 3.04 The stratified grammar that removes it



```ebnf

UnionExpr ::= Primary { ( "union" | "minus" ) Primary }

Primary   ::= "(" UnionExpr ")" | IDENT

```



There is now exactly one derivation `UnionExpr` cannot appear as a direct child of `UnionExpr` except inside parentheses, so the nesting seen in Tree 2 is unreachable, the loop is folded left-to-right, which forces tree 01: `(A union B) minus C`



\### 3.5 Case   11- `A minus B minus C`  



Documented rule: left-associative hense `(A minus B) minus C`



Instance where the other grouping is different:



```

A (x) = { 1, 2 }

B (x) = { 1 }

C (x) = { 2 }

```



| Grouping | Evaluation | Result |

|---|---|---|

| `(A minus B) minus C` (mine) | `{2} minus {2}` | `{ }` |

| `A minus (B minus C)` | `{1,2} minus {1}` | `{ 2 }` |



Set difference is not associative, so this is not a matter of taste but one of the two has to be chosen and written down.



\---



\## 4.00 Parsing strategy

Strategy: hand-written recursive descent, one function per non terminal.



\### 4.01 Why



The grammar above is LL(1) after stratification so at every decision point one token of lookahead is enough to pick an alternative. Recursive descent then maps mechanically onto it: `UnionExpr` becomes `parse\_union\_expr()`, `AndCond` becomes `parse\_and\_cond()`, and so on ... 3 things follow from that



1\. The call stack is the parse tree, so the code is checkable against this document line

&#x20;  by line

2\. Error positions are free, the current token carries its offset, so a failure reports

&#x20;  where it happened rather than throwing (sect 6.3 of the spec)

3\. precedence lives in the shape of the grammar, so adding an operator level means adding

&#x20;  one function, not patching conditionals inside another existing one



\#### 4.02 What left recursion does to it



A rule of the form `Expr ::= Expr "union" Expr` compiles to a function whose first action is to call itself, on the same input, having consumed nothing. That recurses forever and overflows the stack. Recursive descent cannot handle left recursion at all not slowly, nor random, it simply doesnt terminate.



Where I removed it:: The naive grammar in Section 3.1 is left recursive in both alternatives. The stratified rules in sect 1.2 replace every left recursive rule with the iterative form below



```

left-recursive:   UnionExpr ::= UnionExpr ( "union" | "minus" ) IntersectExpr

rewritten:        UnionExpr ::= IntersectExpr { ( "union" | "minus" ) IntersectExpr }

```



The `{ ... }` is a loop, not a recursive call, so the function parses one operand, then iterates while it sees a matching operator, folding left as it goes. Same language but  identical left associative trees, terminates



`UnionExpr`, `IntersectExpr`, `ProductExpr`, `OrCond` and `AndCond` all use this form. 'NotCond` is the one deliberately right-recursive rule, prefix operators recurse on the right, which is safe, because the token `not` is consumed before the recursive call



\---



\## 5.0 lexical decisions



These are scanner level rules that the grammar above depends on



\### 5.01 Maximal munch



On reading `>`, the scanner looks at the next character before committing: `>=` produces one `GE` token, anything else produces `GT` and does not consume the lookahead. Same for `<`/`<=` and `!`/`!=`. (`!` alone is a lexical error, there is no negation operator spelled that way.) seen in case 3.



\### 5.2 negative numbers case 04



`select\[Age>-30](R)` must scan as `Age`, `>`, `-30`. Maximal munch must not manufacture a `>-` operator, because no such operator exists in the operator table; the scanner only extends a token while the extension is itself a legal token.



The language has no arithmetic, so `-` is never a binary operator. rule: a `-` immediately followed by a digit begins a `NUMBER`. Unambiguous precisely because there is nothing else `-` could mean.



\### 5.03 Keywords are contextual (soft keywords) seen in case 8



`select\[union=3](R)` must work: `union` is a legal attribute name.



the rule: the scanner never reserves a word. Every word shaped run of characters becomes an `IDENT` carrying its text. The parser decides whether an `IDENT` is an operator based onthe position:



\-In `UnionExpr`, after a complete operand, an `IDENT` whose text is `union` or `minus` is a binary operator.

\- In `Operand` position, any `IDENT` is an attribute reference, whatever it spells.



So in `select\[union=3](R)`, the parser is at `Operand` when it sees `union` and reads it as an attribute. In `A union B`, the parser has a complete operand and is looking for an operator, so it reads it as one



Documented consequence: a relation named `union` can be defined and referenced thgough `A union B` where `union` is also a relation name is read as the operator, because the operator test is applied first in that position. I accept this; the alternative is lookahead that buys nothing



\### 5.4 Strings     for cases 5, 6, 7, 9



`STRING` begins at `'` and the scanner consumes characters until a closing `'`, with `''` inside consumed as one literal `'`. Because the scanner runs over the raw character stream in one pass, `'Bob)'` and `'a,b'` are single tokens and their `)` and `,` are never

seen as punctuation. Any approach that balances parentheses or splits on commas before tokenizing fails in cases 5 , 6.



Hitting end ofinput or end of line before the closing quote is a lexical error reporting the offset of the opening quote (seen in case 9)



\### 5.05 positions



Every token carries `(offset, line, column)`. This is what makes the error messages in section 6.3 of the spec possible and it costs nothing to record at scan time and is painful to reconstruct later



\---



\## 6.0 Sources

Nystrom, Crafting Interpreters, "Scanning" (https://craftinginterpreters.com/scanning.html) — read this to see the character by character scanning loop, which is the pattern tokenizer.py follows: read one character, decide what kind of token is starting, keep consuming until it ends.





Nystrom, Crafting Interpreters, "Parsing Expressions" (https://craftinginterpreters.com/parsing-expressions.html) — this is where I got the idea for splitting the grammar into precedence levels that call each other (UnionExpr calls IntersectExpr calls ProductExpr calls Primary), which is what Section 1.2 of this file is built on. 





Wikipedia, "Extended Backus–Naur form" (https://en.wikipedia.org/wiki/Extended\_Backus%E2%80%93Naur\_form) — used this to check my EBNF in Section 1 is using standard notation.



Wikipedia, "Recursive descent parser" (https://en.wikipedia.org/wiki/Recursive\_descent\_parser) — confirmed that "one function per non-terminal" is the actual definition of this parsing strategy not just how I happened to organize parser.py.





Wikipedia, "Maximal munch" (https://en.wikipedia.org/wiki/Maximal\_munch) — this is where the term for what \_operator does with > vs >= comes from (checking next character before deciding which token you made).





Wikipedia, "Operator-precedence parser" (https://en.wikipedia.org/wiki/Operator-precedence\_parser) — background for why precedence levels can be encoded as nested function calls the way Section 1.2 does it.





Wikipedia, "Dangling else" (https://en.wikipedia.org/wiki/Dangling\_else) — this is a  well known  version of the exact ambiguity problem I had to demonstrate in Section 3 with A union B minus C. Reading this helped me see that my ambiguity example isn't a one-off quirk of this assignment, it's the same shape of problem that shows up in real languages like C, and the standard fix (attach to the nearest thing) is the same left  associative instinct my stratified grammar uses.





Wikipedia, "Ambiguous grammar" (https://en.wikipedia.org/wiki/Ambiguous\_grammar) — gave me the actual definition I used in Section 3: a grammar is ambiguous if some string has two different parse trees, which is exactly what I had to show for A union B minus C.





Rust Reference, "Keywords" §Weak Keywords (https://doc.rust-lang.org/reference/keywords.html#weak-keywords) — Rust's own list of weak keywords includes union, which is the exact word my case 8 test (select\[union=3](R)) uses. Reading how Rust handles this confirmed my approach in Section 5.3: the tokenizer never reserves a word, and whether an IDENT is treated as an operator or a name depends on where it shows up in the grammar, not on the word itself. Rust calls this a "weak keyword"; I didn't know that term before reading this.





Wikipedia, "LL grammar" (https://en.wikipedia.org/wiki/LL\_grammar) — this is the formal name for the property my grammar actually has: at every point the parser needs to decide something, one token of lookahead is enough. That's the real reason recursive descent works cleanly here instead of just seeming to work



Where AI was wrong: The full details are in DESIGN\_LOG.md. In short, there were a few mistakes in the AI generated code. The first version of \_infer\_types in catalog.py mixed up two different checks and only worked by accident. The first version of join also stored the whole cross product in memory before filtering it, which caused a MemoryError when both relations had 32,000 tuples. The estimated time for the full performance test was also wrong. It was expected to take about an hour, but it actually took around 139 minutes.

