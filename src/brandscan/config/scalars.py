"""Reading YAML scalars without losing what the operator typed.

A company number is a bare numeral, so YAML resolves it to an integer. Coercing
that integer back with `str()` is not safe: PyYAML implements YAML 1.1, where a
leading-zero numeral made only of octal digits is octal, so `07654321` parses to
`2054353`. A scan built from the parsed value would search hundreds of
repositories for a number that appears in none of them and report every one of
them clean — the silent miss that `RepoStatus` exists to make impossible.

So numeric scalars arrive carrying their source text, and every string-valued
field is built from that text rather than from the parsed value.

Only `int` and `float` are wrapped. `bool` cannot be: Python forbids
subclassing it, so a raw-carrying boolean would have to subclass `int`, at which
point `isinstance(value, bool)` is false for it — `include_archived: true` would
be rejected as not a boolean, and `similarity_threshold: true` would slip past
the guard that currently stops it and be accepted as `1`. Booleans are therefore
left untouched and stay inadmissible where a string is expected; an operator who
means the word writes it quoted.
"""

from __future__ import annotations

from typing import Any, Callable

import yaml


class RawInt(int):
    """An integer that remembers the text it was written as."""

    raw: str


class RawFloat(float):
    """A float that remembers the text it was written as."""

    raw: str


class RawScalarLoader(yaml.SafeLoader):
    """`SafeLoader`, but numeric scalars keep their source text.

    Subclassing rather than composing the node tree by hand keeps PyYAML's
    anchor, alias, and merge handling intact — the parse is unchanged, only the
    two numeric constructors are decorated.
    """


def _raw_constructor(
    wrapper: type, construct: Callable[[Any, Any], Any]
) -> Callable[[Any, Any], Any]:
    def constructor(loader: Any, node: Any) -> Any:
        value = wrapper(construct(loader, node))
        value.raw = node.value
        return value

    return constructor


RawScalarLoader.add_constructor(
    "tag:yaml.org,2002:int",
    _raw_constructor(RawInt, yaml.SafeLoader.construct_yaml_int),
)
RawScalarLoader.add_constructor(
    "tag:yaml.org,2002:float",
    _raw_constructor(RawFloat, yaml.SafeLoader.construct_yaml_float),
)


def load_yaml(text: str) -> Any:
    """Parse YAML, preserving the source text of every numeric scalar."""
    return yaml.load(text, Loader=RawScalarLoader)


def scalar_text(value: Any) -> str | None:
    """The string a value contributes to a string-valued field, or `None`.

    `None` means inadmissible, leaving the caller to raise its own field-named
    error rather than guessing at one here.

    Booleans and `None` are inadmissible. An empty list entry parses as `None`,
    and admitting it as `''` would produce a pattern matching every file
    scanned; YAML's boolean words are almost always a stray unquoted value.

    A numeric that carries no source text was not parsed from YAML — it came
    from a caller passing a plain `dict`. `str()` is lossless there, because a
    Python integer literal cannot carry a leading zero in the first place.
    """
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        raw = getattr(value, "raw", None)
        return raw if isinstance(raw, str) else str(value)
    return None
