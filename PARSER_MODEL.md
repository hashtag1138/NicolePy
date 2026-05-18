# PARSER_MODEL.md

## Status

This document is not normative.
It is an implementation model for the Nicole Python parser.

The normative source is exclusively the Nicole specification repository:

- `https://github.com/hashtag1138/Nicole`
- `SYNTAXE.md`
- `SEMANTIQUE.md`
- `HOST_ABI.md`

The public examples are also useful consolidation material:

- `EXAMPLES.md`
- `INVALID_EXAMPLES.md`

Implementation follows specification, never the inverse.

## 1. Parser Boundary

Parser input:

- a sequence of `Token`

Parser output:

- a syntax tree

Parser responsibility:

- recognize the syntactic shape of Nicole source
- preserve source order
- build a structured AST
- report syntax errors only

Parser non-responsibility:

- name resolution
- type checking
- stack-effect checking
- host binding validation
- export-name validation
- visible-name collision validation
- exhaustiveness checking
- semantic interpretation

## 2. Syntax Forms the Parser Must Recognize

The parser must recognize the syntax of:

- program structure
- word definitions
- `pub` and `export`
- signatures of the form `{ inputs -- outputs }`
- parameters of the form `name:Type`
- simple types
- generic types
- quotation types `Quote<{ captures | inputs -- outputs }>`
- concatenative bodies
- nested subwords
- `if ... else ... end`
- `case ... end`
- branches of the form `pattern => body`
- quotations of the form `:[ captures | inputs -- outputs | body ;]`
- literals
- identifiers
- naked identifier calls
- primitive operators as body atoms
- float arithmetic operators such as `+.` `-.` `*.` `/.`
- list literals such as `[1]` and `[1, 2]`
- typed empty list construction `[]:List<T>`
- typed empty map construction `map.empty:Map<K,V>`

The parser must reject or leave for later validation only what is actually semantic.
Pure syntax errors belong here.

## 3. What the Parser Must Not Decide

The parser does not decide:

- whether `List<Int>` is a valid type
- whether `host.log` exists
- whether `app.on-message` is a valid export target for the integration contract
- whether `+` accepts the right types
- whether `+.` or `/.` accept the right types
- whether `case` is exhaustive
- whether the `if` branches have the same stack effect
- whether `list.reduce` is called on a non-empty list
- whether a quotation body is well typed
- whether quotation captures are available
- whether a directly called `host.*` word is present in the known host contract

Visible-name collisions may be detected later by signature collection or resolution.
Frame-local name collisions are rejected by the current parser because frame declarations are structural syntax forms in the active implementation.
That includes:

- duplicate inputs in one word signature
- duplicate quotation captures
- duplicate quotation inputs
- duplicate quotation capture/input names inside one quotation frame

The parser still allows the same local name to appear again in a different frame.
Examples of valid different-frame reuse include:

- parent word local name reused by a nested subword
- constructing-word local name reused as the explicit capture name of a quotation

## 4. AST Model

The parser should produce a syntax tree with explicit nodes.

### ProgramNode

Represents a complete Nicole source unit.
Contains the parsed top-level words.

### WordDefNode

Represents one word definition.
Contains:

- the word name
- visibility information
- the signature
- the body
- any nested subwords

### SignatureNode

Represents a parsed signature.
Contains ordered input parameters and ordered output parameters.

### ParameterNode

Represents one `name:Type` entry in a signature.

### TypeNode

Represents a syntactic type form.

### QuoteTypeNode

Represents the syntax of `Quote<{ captures | inputs -- outputs }>` inside a type position.

The parser preserves captures and inputs as distinct syntactic zones.
The current parser also rejects duplicate local names inside the quotation frame represented by those zones.
It therefore rejects:

- duplicate capture names
- duplicate input names
- any duplicate name shared between the capture zone and the input zone

### BlockNode

Represents an ordered body.
It preserves order and nesting only.

### AtomNode

Represents one syntactic element in a block.

### IdentifierNode

Represents a bare identifier token used as a body atom or a call target.

### OperatorNode

Represents a primitive or operator written directly in a body.
Examples include stack primitives, integer arithmetic operators, float arithmetic operators, comparisons, and `call`.

### LiteralNode

Represents a parsed literal.

### ListLiteralNode

Represents a non-empty or element-bearing list literal such as `[1]` or `[1, 2]`.

The implementation may represent `[]:List<T>` either as:

- a specialized typed-empty-list node
- a `ListLiteralNode` plus an explicit trailing type annotation node

The exact shape is an implementation detail.
What matters is that the parser distinguishes the typed empty form from bare `[]`.

### TypedEmptyMapNode or Equivalent

The parser must preserve `map.empty:Map<K,V>` as an explicit typed-empty-map construction.

This must not be modeled as a normal naked builtin call with no type annotation.

### IfNode

Represents the structured branch opened by `if`.
It contains only the two branch blocks.

### CaseNode

Represents the structured branch opened by `case`.
It contains only the ordered list of branches.

### CaseBranchNode

Represents one `pattern => body` branch inside a `case`.

### PatternNode

Represents one parsed pattern form.
It may cover:

- literal patterns
- `_`
- `Ok(v)`
- `Err(e)`
- `Err(MissingKey)`
- `Err(OutOfBounds)`
- `MissingKey`
- `OutOfBounds`

### QuoteNode

Represents a quotation literal beginning with `:[` and ending with `;]`.
Contains captures, inputs, outputs, and the quotation body.

The parser preserves explicit stack capture.
It must not reinterpret a quotation as lexically capturing parent locals.

## 5. Concatenative Bodies

A word body is a syntax-preserving sequence of atoms:

- identifiers
- literals
- operators
- subwords
- quotations
- `if`
- `case`
- list constructions
- typed empty constructions

The parser must keep body order exactly as written.
It must not compute stack effects or reduce the body to semantic meaning.

## 6. Types

The parser must build a syntax tree for types.
It must recognize forms such as:

- `Int`
- `String`
- `List<Int>`
- `Map<String,Int>`
- `Result<Int,MapError>`
- `Quote<{ | x:Int -- y:Int }>`
- `Quote<{ a:Int | x:Int -- y:Int }>`

The parser uses `<`, `>`, `,`, `{`, `}`, `|`, and `--` as syntactic structure.
It does not decide whether the resulting type is semantically valid.

## 7. Quotations

The lexer provides quotation tokens for `:[` and `;]`.

The parser recognizes the canonical quotation form:

```sorte
:[ captures | inputs -- outputs | body ;]
```

Important parser-facing facts:

- `]` alone is not a valid quotation terminator
- captures are declared at construction time
- inputs and outputs are part of the quotation syntax
- quotation bodies are concatenative blocks
- quotations are separate frames from the constructing word
- duplicate local-name detection inside one frame is a later validation step

## 8. `case`

The parser must recognize the syntax:

```sorte
value case
  pattern => body
end
```

It must also preserve the fact that v1 has no guards:

- `when` is not part of the syntax

## 9. Name Collisions

The parser may keep structure only and leave collision detection to signature collection.
It must not document same-name multiple definitions as a valid language feature.

Invalid examples according to the public specification include:

- two top-level words of the same name
- two words of the same name with different types
- two words of the same name with different arities
- two sibling subwords of the same name
- `pub` / `export` name collisions
- duplicate export names

## 10. Consequences for `parser.py`

`parser.py` should:

- parse syntax only
- preserve body order
- preserve quotation structure
- preserve typed empty constructions
- preserve nested word structure

It should not:

- resolve names
- select among multiple definitions
- perform stack checking
- validate host contracts
- validate export contracts
