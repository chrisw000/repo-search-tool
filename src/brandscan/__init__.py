"""Brand asset discovery scanner.

Finds traces of an old brand across many repositories by image content and by
text pattern, and reports them as fix instructions. It finds and reports only;
it never edits a scanned repository.
"""

__version__ = "0.1.0"

TOOL_NAME = "brandscan"


def tool_version() -> str:
    """Version string recorded in every report's provenance block."""
    return __version__
