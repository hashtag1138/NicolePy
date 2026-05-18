# AST_MODEL.md

## Status

This document is not normative.
It describes the internal AST architecture for the Nicole Python implementation.

The normative source remains exclusively the Nicole specification repository:

- `https://github.com/hashtag1138/Nicole`
- `SYNTAXE.md`
- `SEMANTIQUE.md`
- `HOST_ABI.md`

The public examples are also useful consolidation material:

- `EXAMPLES.md`
- `INVALID_EXAMPLES.md`

Implementation follows specification, never the inverse.

## 1. What the AST Is

The AST is the parser's structured representation of Nicole source.
It sits between tokens and later analysis stages.
Its role is to preserve syntax in a tree shape convenient for resolution, checking, and execution preparation.

The AST does not decide meaning.
It records structure.

## 2. Parser Boundary

The parser receives `Token` objects and produces AST nodes.

Parser output is syntax only.
The parser must not perform:

- name resolution
- type checking
- stack-effect checking
- host validation
- export validation
- semantic evaluation

## 3. Stack-Oriented Shape

Nicole is concatenative and stack-based.
The AST must preserve the order of stack-producing source elements.
It must not convert the language into an expression tree model.

In particular:

- `IfNode` does not own a `condition` expression
- `CaseNode` does not own a `scrutinee` expression

The stack-producing sequence that feeds `if` or `case` remains in the surrounding `BlockNode`.

## 4. AST Node Catalogue

### ProgramNode

Represents a complete Nicole source unit.
Contains the top-level word definitions.

### WordDefNode

Represents one word definition.
Contains:

- the word name
- visibility
- the signature
- the body
- nested definitions when the source contains them

### Visibility

Represents the syntactic visibility of a word:

- private
- `pub`
- `export`

### SignatureNode

Represents a parsed signature of the form `{ inputs -- outputs }`.

### ParameterNode

Represents one `name:Type` entry in a signature.
Local-name uniqueness inside one frame is not guaranteed by the node alone; later validation must enforce it.

### TypeNode

Represents a syntactic type form.

### QuoteTypeNode

Represents `Quote<{ captures | inputs -- outputs }>` in a type position.
It preserves captures, inputs, outputs, and ordering.
The presence of captures in the type is semantically significant and must not be erased when checking higher-order builtins.

### BlockNode

Represents an ordered concatenative body.

### AtomNode

Represents one syntactic element inside a block.

### IdentifierNode

Represents a bare identifier token used as a body atom or a call target.
It does not resolve the name.

### OperatorNode

Represents an operator or primitive written directly in a body, such as `+`, `-`, `*`, `+.`, `-.`, `*.`, `/.`, `<`, `<=`, `=`, `!=`, `div`, `mod`, `and`, `or`, `not`, `call`, or `drop`.

### LiteralNode

Represents a parsed literal.

### ListLiteralNode

Represents an element-bearing list literal such as `[1]` or `[1, 2]`.

The typed empty form `[]:List<T>` should remain structurally distinct from a bare list literal.

### TypedEmptyListNode or Equivalent

Represents the explicit empty-list construction `[]:List<T>`.

The exact node name is an implementation detail.
The important invariant is that the AST preserves:

- the fact that the list is empty
- the explicit attached type annotation

### TypedEmptyMapNode or Equivalent

Represents the explicit empty-map construction `map.empty:Map<K,V>`.

This must stay distinct from a normal word call.
It is a typed construction, not an ordinary naked builtin invocation.

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

Binding meaning is semantic and checked later, but the AST must preserve the distinction between binding forms and non-binding forms.

### QuoteNode

Represents a quotation literal beginning with `:[` and ending with `;]`.
Contains captures, inputs, outputs, and the quotation body.
It represents an explicit stack-capturing anonymous word, not an implicit lexical closure over parent locals.

## 5. Resolved AST Annotation

The AST remains the structural tree produced by the parser.
The resolver does not replace the AST.
It annotates existing nodes with resolution metadata in place.

Typical targets for annotation include:

- `IdentifierNode`
- explicit call targets

The annotation may contain:

- resolved symbol
- owner scope
- qualified name
- visibility
- signature reference

A resolved identifier must designate one symbol or else the program is invalid.
There is no language feature where one visible name intentionally resolves to several alternative definitions.

## 6. What Nodes Must Not Do

AST nodes are structural.
They must not:

- resolve names
- infer types
- check stack effects
- validate host bindings
- validate exports
- evaluate programs
- decide exhaustiveness

## 7. Quotations and Typed Empties

The AST should preserve three important current v1 decisions:

- value quotations close with `;]`
- `[]:List<T>` is valid and bare `[]` is invalid
- `map.empty:Map<K,V>` is valid and bare `map.empty` is invalid
- local names must later be validated as unique inside each frame

The exact internal node split is an implementation choice, but those distinctions must survive parsing.

## 8. Source Spans

Every AST node should carry a `SourceSpan` or equivalent source location metadata.
The span exists for diagnostics only.

## 9. Consequences for `ast_nodes.py`

`ast_nodes.py` should remain small, explicit, and structural.
It should provide node types for:

- program
- word definitions
- signatures and parameters
- types and quotation types
- blocks
- identifiers, literals, and operators
- `if`
- `case`
- quotations
- typed empty constructions, either directly or through an explicit equivalent representation
