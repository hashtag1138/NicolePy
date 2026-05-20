# LEXICAL_MODEL.md

This document defines the lexical layer for the Nicole Python implementation.
It is not normative.

The lexer only turns source text into tokens with source positions.
It does not resolve names.
It does not type-check.
It does not validate host bindings.
It does not validate visible-name collisions.
It does not perform semantic analysis.

Implementation follows specification, never the inverse.

## 1. Lexer Boundary

Lexer input:

- source text

Lexer output:

- a sequence of tokens

Lexer responsibility:

- split text into lexical units
- classify each unit
- attach source position metadata

Lexer non-responsibility:

- whether a word exists
- whether a visible name collides with another definition
- whether an invocation is valid
- whether a type is correct
- whether `host.*` is available
- whether a directly called `host.*` word is missing from the known host contract
- whether an export name is unique
- whether `case` is exhaustive
- whether a quotation is well typed

## 2. Token Categories

The lexer recognizes these categories:

- punctuation
- syntax operators
- modifiers and keywords
- identifiers
- literals
- primitive operators
- end of file

### Punctuation

Examples:

- `:`
- `;`
- `{`
- `}`
- `[`
- `]`
- `(`
- `)`
- `|`
- `<`
- `>`
- `,`

The lexer may also provide dedicated multi-character tokens when that keeps parsing simpler.

### Syntax Operators

Examples:

- `--`
- `=>`
- `:[`
- `;]`

### Modifiers and Keywords

Examples known from the specification:

- `pub`
- `export`
- `if`
- `else`
- `end`
- `case`
- `_`

### Identifiers

Examples:

- `add`
- `list.map`
- `map.get`
- `host.log`
- `app.on-message`

The lexer recognizes the shape of an identifier.
It does not decide whether the identifier is legal in a given semantic context.

Current lexical constraints tracked from the public specification:

- an identifier starts with an ASCII letter or `_`
- later characters may include ASCII letters, digits, `_`, `-`, and `.`
- `-` may appear inside an identifier such as `captured-offset`, but bare `-` remains an operator
- `.` belongs to qualified names such as `host.log`; it is not a standalone operator

### Literals

Examples:

- integers
- floats
- strings
- booleans

Current string-literal constraints tracked from the public specification:

- strings use double quotes
- raw newline characters are not part of a valid string literal
- escapes include at least `\\\"`, `\\\\`, `\\n`, and `\\t`

### Primitive Operators

Examples:

- `+`
- `-`
- `*`
- `+.`
- `-.`
- `*.`
- `/.`
- `=`
- `!=`
- `<`
- `<=`
- `drop`

These are tokenized, not validated.
The lexer must not imply that bare `/` is a v1 arithmetic operator if the current specification reserves floating arithmetic for `/.`.

## 3. Special Cases

### `host.*`

The lexer recognizes `host.log`, `host.read-file`, and similar forms as identifiers.

It does not decide:

- whether the host word exists
- whether a directly called host word is present in the known contract
- whether optionality is relevant under a future explicit mechanism
- whether the usage is valid

### Generic Types

Examples:

- `List<Int>`
- `Map<String, Int>`
- `Result<V, E>`
- `Quote<{ captures | inputs -- outputs }>`
- `DirtyQuote<{ captures | inputs -- outputs }>`

The lexer does not understand these as types.
It only tokenizes their pieces.

### Quotations

Example:

```sorte
:[ x:Int | y:Int -- z:Int | body ;]
```

The lexer only splits the text into tokens.
It does not validate quotation typing or capture legality.
The quotation start `:[` and quotation end `;]` should be tokenized explicitly enough for the parser to distinguish them from ordinary `:` `[` `;` `]` sequences.

The lexer also does not decide whether quotation capture names and quotation input names collide.
That is a later frame-validity check.

### Typed Empty Constructions

Examples:

- `[]:List<Int>`
- `map.empty:Map<String,Int>`

The lexer tokenizes these as ordinary lexical pieces:

- `[` `]` `:` `List` `<` `Int` `>`
- `map.empty` `:` `Map` `<` `String` `,` `Int` `>`

The lexer does not decide whether the unannotated forms are invalid.

## 4. Source Positions

Each token must carry source location data.

Required fields:

- line
- column
- character offset

## 5. Lexical Errors

The lexer may report only lexical failures:

- invalid character
- unterminated string
- impossible token
- impossible lexical structure

The lexer must not report:

- type errors
- stack errors
- host contract errors
- export-name collisions
- visible-name collisions

## 6. Non-Goals

The lexer is not:

- name resolution
- type inference
- stack checking
- host validation
- export validation
- semantic analysis
- a parser in disguise

## 7. Consequences for `tokens.py`

`tokens.py` should stay small and explicit.

It should provide at least:

- `TokenKind`
- `Token`
- `SourceSpan`

That separation keeps lexing independent from parsing and checking.
