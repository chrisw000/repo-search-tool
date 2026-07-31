## Context

See proposal.md — Why. The constraints that shape the approach:

- `_string_list` in `src/brandscan/config/loader.py` is the single funnel every
  string list passes through. `_parse_targets`, `_parse_group_overrides`, and
  `_parse_scope` all call it, so one change reaches every position the spec names.
- The same file validates genuinely typed fields with `isinstance` checks that
  lean on Python's type lattice — notably `isinstance(x, int) and not
  isinstance(x, bool)` for `similarity_threshold` and `scope.max_file_bytes`.
  Anything that alters what those `isinstance` calls see is a regression risk in
  exactly the fields the second requirement protects.
- `validate_config` is public and takes a plain `dict`. `load_config` is the only
  caller in `src/`, but the test suite constructs dicts directly, so a value can
  arrive with no source text to preserve.
- PyYAML is already the only YAML dependency; nothing new is needed.

Measured against the current code, so the design is not reasoning from the spec
alone:

| written | PyYAML gives | today |
| --- | --- | --- |
| `03909886` | `'03909886'` | accepted — the resolver matches neither its octal nor its decimal branch |
| `3909886` | `3909886` | rejected |
| `07654321` | `2054353` | rejected, **and the digits are already lost** |

## Goals / Non-Goals

**Goals:**

- One coercion point, so every string-list position behaves identically and a
  future position inherits the behaviour by construction.
- The source text survives from the file to the compiled pattern, with no step
  that could substitute a re-rendered value.
- Typed-field validation comes out of this change no weaker than it went in,
  demonstrated by tests rather than asserted.

**Non-Goals:**

- Changing which fields are string-valued, or introducing new ones.
- Coercing in the other direction — a quoted `"10"` in an integer field stays an
  error.
- Rescuing values PyYAML cannot round-trip at all, such as a timestamp scalar.
  Numeric scalars are the reported need; anything further is speculative.

## Decisions

### D1 — Coerce at the string-list boundary, not by disarming the parser

`_string_list` gains the coercion; the parse stays fully typed.

*Alternative rejected:* strip the implicit `int`/`float`/`bool` resolvers from the
loader so every scalar arrives as a string. It fixes string lists by breaking
everything else — `similarity_threshold` and `max_file_bytes` would arrive as
`'10'` and fail their own validation, and each would need a re-parse that
reintroduces the coercion problem in the opposite direction. Keeping the document
typed and narrowing at the one place that wants strings is the smaller blast
radius.

### D2 — Carry the source text on an `int`/`float` subclass

`load_config` reads through a `yaml.SafeLoader` subclass whose `int` and `float`
constructors return a subclass instance carrying the node's `value` — the
unmodified source text — on a `raw` attribute. `_string_list` prefers `raw`.

This is chosen over composing the node tree and walking it manually, which would
mean reimplementing PyYAML's merge, alias, and anchor handling to get at the same
strings; and over re-reading the file to locate the original token, which is
fragile against flow style, comments, and multi-document files.

The subclass matters because it keeps `isinstance(x, int)` true. Every existing
integer check continues to hold without being touched, which is what makes this
safe to apply to a shared loader rather than to a bespoke parse.

Verified against PyYAML before adopting: `07654321` arrives as a value equal to
`2054353` carrying `raw == '07654321'`, and `similarity_threshold: 10` still
satisfies `isinstance(x, int) and not isinstance(x, bool)`.

### D3 — Wrap `int` and `float` only; leave `bool` alone

The prototype showed why this is not symmetric. Python forbids subclassing
`bool`, so a raw-carrying boolean can only subclass `int` — at which point
`isinstance(value, bool)` is **false** for it. Two failures follow immediately:
`include_archived: true` would be rejected as not a boolean, and
`similarity_threshold: true` would slip through the `not isinstance(x, bool)`
guard and be accepted as `1`. The second is a direct violation of the
requirement that typed fields not be weakened.

Recovering from that would mean rewriting all five boolean and integer checks
around helper predicates — more edits, in the code this change is supposed to
leave provably intact, to buy admission for YAML's boolean words (`No`, `on`,
`yes`) as brand vocabulary. That is a hypothetical need against a real risk.

Consequence, stated so it is not discovered later: a bare `No` in a string list
is still rejected with the field-named error, and the operator quotes it. The
error already says what to do.

### D4 — Plain numerics without source text coerce with `str()`

When a value has no `raw` — a dict built in a test, or by any caller that parsed
the YAML itself — `_string_list` falls back to `str(value)`.

This is lossless for the case it serves. A Python integer literal cannot carry a
leading zero at all (`0123456` is a syntax error), so a dict-constructed `3909886`
has no lost digits to recover; `str()` returns exactly what the caller meant. The
lossy case only exists inside YAML parsing, and every YAML path goes through the
loader from D2.

*Alternative rejected:* keep rejecting values without `raw`. It would force every
test of this behaviour to go through a temporary file, testing the loader instead
of the validator, and would make the public `validate_config` reject input the
file path accepts for no reason the caller could act on.

### D5 — `None` stays a rejection

An empty list entry resolves to `None`. Coerced, it would become either `''` — a
pattern matching every file in the estate — or the literal `'None'`. Both are
worse than the current field-named error, and neither is what anyone typed. It is
almost always a stray `-` in the YAML.

### D6 — Normalise on the way into `Config`

`scope.max_file_bytes` and `similarity_threshold` are cast with `int()` before
being stored, so no raw-carrying subclass escapes the loader into the rest of the
system. `similarity_threshold` already does this; `max_file_bytes` gains it. This
keeps the seam at the config boundary, so nothing downstream — reporting, the run
log, the JSON sidecar — can encounter a type it was not written for.

### D7 — Reference-image labels use the same helper

`references.py` builds labels with `str(v)`, which carries the identical defect: a
numeric label loses its digits silently. It is a lower-stakes field — a label
names a layout in a report rather than driving a search — but it is the same bug,
and leaving one instance behind means the next reader has to work out why two
neighbouring coercions differ. The sidecar reads through the same loader and the
same `scalar_text` helper.

## Risks / Trade-offs

- **A wrapped numeric escapes the loader and reaches code that type-switches on
  `int`** → D6 casts at the `Config` boundary. `RawInt` is an `int` and
  `RawFloat` is a `float`, so arithmetic, comparison, and formatting all behave
  identically even if one did escape; the cast is belt-and-braces, not the only
  defence.
- **Serialisation of a wrapped value** — the JSON sidecar and JSONL run log both
  serialise config-derived values. `json` serialises an `int` subclass as a
  number, so no failure, but D6 removes the question entirely.
- **`0x1F` and `1_000` are now admitted as the literal strings `0x1F` and
  `1_000`** rather than `31` and `1000`. This follows from the rule and is the
  right answer — the operator gets what they typed — but it is a behaviour
  someone could find surprising. It replaces a hard error, so nothing that
  worked before changes.
- **Silent success where there used to be a loud failure** → the mitigation is
  that the value used is always the value written, so there is nothing for the
  operator to be misled about. Existing reporting already records the patterns a
  run searched for.

## Migration Plan

None required. Every configuration valid today stays valid and produces identical
patterns; the change only admits input that previously aborted the run. No stored
state, no output-format change, and rollback is reverting the commit.
