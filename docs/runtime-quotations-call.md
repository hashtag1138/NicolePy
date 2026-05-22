# Runtime Quotations and `call`

NicolePy supports runtime quotations and `call` through the checked AST runtime.

## Execution model

The canonical flow is:

```python
checked = analyze_program(source, host_contract=host_contract)
run_export(checked, "@app.run", runtime_bindings)
```

The runtime consumes only `CheckedProgram`.
It does not re-parse, re-resolve, or re-check source.

## Quotation values

A quotation is a runtime value carrying:

- declared captures
- declared inputs
- declared outputs
- the checked Nicole block to execute when `call` is used

Quotation types are `Quote<{ captures | inputs -- outputs }>` and `DirtyQuote<{ captures | inputs -- outputs }>`.

## Basic syntax

```nicole
:[ | x:Int -- y:Int | x 1 + ;]
```

Example with a module-contained export:

```nicole
module @app
  : run { -- first:Int second:Int }
    :[ | -- first:Int second:Int | 1 2 ;]
    call
  ;

  export : run
end-module
```

`run_export(...)` returns:

```text
(1, 2)
```

## Captures

Captures are explicit stack captures.
They are stored in the quotation value and are not supplied again at `call` time.

```nicole
module @app
  : run { -- n:Int }
    5
    10
    :[ a:Int | x:Int -- y:Int | a x + ;]
    call
  ;

  export : run
end-module
```

Here:

- `a:Int` captures `10`
- `x:Int` is supplied later as the `call` input `5`
- the result is `15`

## Multiple inputs

`call` consumes quotation inputs in the order declared by the quotation signature.

```nicole
module @app
  : run { -- n:Int }
    10 3
    :[ | x:Int y:Int -- z:Int | x y - ;]
    call
  ;

  export : run
end-module
```

## Nested quotations

Nested quotations are values and are not auto-executed.

```nicole
module @app
  : run { -- q:Quote<{ | -- n:Int }> }
    :[ | -- q:Quote<{ | -- n:Int }> | :[ | -- n:Int | 1 ;] ;]
    call
  ;

  export : run
end-module
```

`Quote` and `DirtyQuote` do not cross the host ABI in v1.

## Calling Nicole words

Quotations may call ordinary Nicole words in the same module.

```nicole
module @app
  : plus-one { x:Int -- y:Int }
    x 1 +
  ;

  : run { -- n:Int }
    5
    :[ | x:Int -- y:Int | x plus-one ;]
    call
  ;

  export : run
end-module
```

## Calling `host.*`

Quotations may call `host.*` words when a host contract is present.

```nicole
module @app
  : log-it { msg:String -- }
    msg host.log
  ;

  : run { -- }
    "hello"
    :[ | msg:String -- | msg log-it ;]
    call
  ;

  export : run
end-module
```

## Runtime errors

Controlled runtime errors are raised for:

- `call` on a non-quotation value
- runtime stack underflow
- malformed runtime quotation values
- host binding failures
- unsupported runtime features

## Notes

- `call` on `Quote` is pure
- `call` on `DirtyQuote` is dirty
- the runtime remains direct AST execution; there is no VM, IR, or bytecode
