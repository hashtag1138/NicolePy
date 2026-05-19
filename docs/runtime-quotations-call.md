# Runtime Quotations and `call`

NicolePy now supports runtime quotations and `call` as a minimal direct-AST runtime feature.

## What a quotation is

A quotation is a checked value that packages a block of Nicole code together with its declared captures, inputs, and outputs.
It is a runtime value, not a special parser-only construct.

Quotations are written with the existing Nicole syntax:

```nicole
:[ | x:Int -- y:Int | x 1 + ;]
```

## Runtime model

NicolePy still executes code through the canonical static/runtime pipeline:

```python
checked = analyze_program(source, host_contract=host_contract)
run_export(checked, "app.run", runtime_bindings)
```

The runtime consumes only `CheckedProgram`.

Quotations are checked statically before runtime.
`call` does not parse source.
`call` does not run the checker.
There is no IR, VM, or bytecode.
Runtime quotations are part of the direct AST runtime.

## Quotation values

When a quotation literal is encountered at runtime, NicolePy pushes a quotation value onto the stack.
The quotation body is not executed immediately.

`call` explicitly executes the quotation value later.

## Basic syntax

The quotation syntax has three sections:

- captures
- inputs
- outputs

Example:

```nicole
:[ a:Int | x:Int -- y:Int | a x + ;]
```

In this example:

- `a:Int` is a capture
- `x:Int` is a call input
- `y:Int` is a declared output

## Inputs and outputs

Quotation inputs are popped from the runtime stack when `call` executes the quotation.
Quotation outputs are pushed back onto the caller stack in declared order.

For multiple outputs, `run_export(...)` returns a tuple.

Example:

```nicole
export : app.run { -- first:Int second:Int }
  :[ | -- first:Int second:Int | 1 2 ;]
  call
;
```

`run_export(...)` returns:

```text
(1, 2)
```

## Captures

Captures are explicit stack captures.
They are part of the quotation value and are not supplied again at `call` time.

The runtime uses the same capture order already enforced statically.

Capture example:

```nicole
export : app.run { -- n:Int }
  5
  10
  :[ a:Int | x:Int -- y:Int | a x + ;]
  call
;
```

Here:

- `a:Int` captures `10`
- `x:Int` is supplied later as the `call` input `5`
- the result is `15`

## Multiple inputs

`call` consumes quotation inputs in the order declared by the quotation signature.

Example:

```nicole
export : app.run { -- n:Int }
  10 3
  :[ | x:Int y:Int -- z:Int | x y - ;]
  call
;
```

Result:

```text
7
```

The example is intentionally non-commutative so input order is visible.

## Nested quotations

Nested quotations are values.
They are not auto-executed.

To execute a nested quotation, `call` must be used explicitly.

Example:

```nicole
export : app.run { -- q:Quote<{ | -- n:Int }> }
  :[ | -- q:Quote<{ | -- n:Int }> | :[ | -- n:Int | 1 ;] ;]
  call
;
```

The result is a quotation value.
It is only executed if `call` is used again.

## Calling Nicole words

Quotations may call ordinary Nicole words.

Example:

```nicole
: plus-one { x:Int -- y:Int }
  x 1 +
;

export : app.run { -- n:Int }
  5
  :[ | x:Int -- y:Int | x plus-one ;]
  call
;
```

## Calling `host.*`

Quotations may call `host.*` words when a host contract is present.

The same runtime bridge applies inside quotations.

Minimal example:

```nicole
: log-it { msg:String -- }
  msg host.log
;

export : app.run { -- }
  "hello"
  :[ | msg:String -- | msg log-it ;]
  call
;
```

## Runtime errors

Controlled runtime errors are raised for:

- `call` on a non-quotation value
- runtime stack underflow
- unsupported runtime features
- malformed runtime quotation values
- host binding failures

## Current limitations

This runtime phase remains intentionally limited:

- collection builtins at runtime are still limited or unsupported where applicable
- higher-order collection builtins such as `list.map`, `list.fold`, and `list.reduce` are not part of this phase
- loops are not implemented
- there is no VM, IR, or bytecode
- there is no optional host fallback
- there is no generalized closure system beyond declared captures

## Short examples

Literal result:

```nicole
export : app.run { -- n:Int }
  :[ | -- n:Int | 42 ;]
  call
;
```

One input:

```nicole
export : app.run { -- n:Int }
  41
  :[ | x:Int -- y:Int | x 1 + ;]
  call
;
```

Capture + input:

```nicole
export : app.run { -- n:Int }
  5
  10
  :[ a:Int | x:Int -- y:Int | a x + ;]
  call
;
```

## Notes

The runtime model is intentionally direct and minimal.
It reuses the already checked AST and does not introduce a new execution framework.
