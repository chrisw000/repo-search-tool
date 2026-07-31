"""Writing a small JSON file so that an interrupt cannot leave it half-written.

Both the checkpoint and the run record are read by the *next* invocation to
decide what work is outstanding. A file truncated by a hard kill is worth
nothing, so each is written to a temporary file in the same directory and moved
into place, which is atomic on both the platforms this runs on.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
