# NicolePy v0.15 Alignment

## Spec baseline
- tag: `v0.15.0-collection-core-spec`
- commit: `67084a65a69d95540f635309b1a77fda4414eee4`

## Major completed work

### Step 1
Documentation/spec target alignment.

### Step 2
Collection-core builtins.
- `list.is-empty`
- `list.first`
- `list.last`
- `list.append`
- `list.reverse`
- `map.is-empty`
- `map.keys`
- `map.values`

### Step 3
Runtime Result propagation (`?`).

### Step 4
Generic `Err!`.

### Step 5
Unit runtime support.

### Step 6
Recursive runtime validation.

### Step 7
Strict v1 type policy.

## Validation
- 624 tests passing.

## Compatibility notes
- Unit now uses `UNIT` sentinel.
- Unknown nominal types rejected.
- Runtime validation now recursive.
