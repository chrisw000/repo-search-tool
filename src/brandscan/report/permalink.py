"""Permalinks into the scanned state.

Pinned to the commit that was actually scanned, never to a branch name. A
report is read days after it is written; a branch-relative link by then points
at a moved line or a deleted file, which makes the finding look wrong rather
than stale.
"""

from __future__ import annotations

from urllib.parse import quote


def blob_permalink(
    host: str,
    org: str,
    name: str,
    commit_sha: str | None,
    path: str,
    line: int | None = None,
) -> str:
    """Build a link to one file, at one commit, on either host.

    GitHub Enterprise Server and github.com share the blob URL shape, so the
    host segment is the only difference between them.
    """
    if not commit_sha:
        return ""
    encoded = "/".join(quote(segment) for segment in path.split("/"))
    url = f"https://{host}/{org}/{name}/blob/{commit_sha}/{encoded}"
    if line:
        url += f"#L{line}"
    return url
