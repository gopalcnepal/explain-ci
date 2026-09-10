import os
import re
from typing import Any

import requests


# Locations the error log points at, in the shapes runners actually emit:
# Python tracebacks, and the path:line[:col] convention used by pytest,
# eslint, tsc, gcc and friends.
_LOCATION_PATTERNS = (
    re.compile(r'File "([^"]+)", line (\d+)'),
    re.compile(r"(?m)^\s*([\w./\\-]+\.\w+):(\d+)(?::\d+)?[:\s]"),
)

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_error_locations(text: str) -> list[tuple[str, int]]:
    """Extract file/line pairs the error log points at.

    Args:
        text: Log text to scan.

    Returns:
        Unique (path, line) pairs in order of first appearance.
    """
    found: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for pattern in _LOCATION_PATTERNS:
        for match in pattern.finditer(text):
            path, raw_line = match.group(1), match.group(2)
            try:
                line = int(raw_line)
            except ValueError:
                continue
            key = (path, line)
            if line > 0 and key not in seen:
                seen.add(key)
                found.append(key)
    return found


def patch_target_lines(patch: str) -> set[int]:
    """Compute which post-change line numbers a patch actually covers.

    GitHub rejects a review comment whose line is not part of the diff,
    so the anchor has to be checked against the hunks first. Added and
    context lines are on the right-hand side; removed lines are not.

    Args:
        patch: Unified diff for a single file.

    Returns:
        Set of right-hand-side line numbers present in the patch.
    """
    lines: set[int] = set()
    position = 0
    for raw in patch.split("\n"):
        header = _HUNK_HEADER.match(raw)
        if header:
            position = int(header.group(1))
            continue
        if position == 0 or raw.startswith("\\"):
            continue
        if raw.startswith("+") or raw.startswith(" ") or raw == "":
            lines.add(position)
            position += 1
        # A '-' line exists only on the left-hand side; position holds.
    return lines


def _same_file(log_path: str, pr_path: str) -> bool:
    """Check whether a log path refers to a repository-relative PR path.

    Runners print absolute paths ('/home/runner/work/repo/repo/a/b.py')
    while the API reports repository-relative ones ('a/b.py').

    Args:
        log_path: Path as it appeared in the log.
        pr_path: Path as reported by the pull request files API.

    Returns:
        True when both paths denote the same file.
    """
    normalized = log_path.replace("\\", "/")
    return normalized == pr_path or normalized.endswith("/" + pr_path)


def find_anchor(
    locations: list[tuple[str, int]],
    files: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick a file/line from the log that is commentable in this PR.

    Args:
        locations: Output of parse_error_locations().
        files: File entries from fetch_pr_files().

    Returns:
        {'path', 'line'} for the first usable anchor, else None.
    """
    usable = [f for f in files if f.get("filename") and f.get("patch")]

    for path, line in locations:
        # An exact or suffix path match is trustworthy; try those first.
        for entry in usable:
            if _same_file(path, entry["filename"]):
                if line in patch_target_lines(entry["patch"]):
                    return {"path": entry["filename"], "line": line}

    for path, line in locations:
        # Fall back to a basename match, but only when it is unambiguous.
        base = os.path.basename(path.replace("\\", "/"))
        matches = [e for e in usable if os.path.basename(e["filename"]) == base]
        if len(matches) == 1 and line in patch_target_lines(matches[0]["patch"]):
            return {"path": matches[0]["filename"], "line": line}

    return None


def upsert_review_comment(
    repo: str,
    pr_number: int,
    headers: dict[str, Any],
    commit_id: str,
    anchor: dict[str, Any],
    body: str,
    marker: str,
) -> bool:
    """Post or update an inline review comment on the anchored line.

    Args:
        repo: Repository in format 'owner/repo'.
        pr_number: Pull request number.
        headers: GitHub API headers (with auth and Accept).
        commit_id: Head SHA the comment is anchored to.
        anchor: {'path', 'line'} from find_anchor().
        body: Full comment body including the marker.
        marker: Hidden marker identifying explain-ci's own comment.

    Returns:
        True when the inline comment was created or updated.
    """
    list_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"

    existing = requests.get(f"{list_url}?per_page=100", headers=headers, timeout=30)
    if existing.status_code == 200 and isinstance(existing.json(), list):
        for comment in existing.json():
            if marker in (comment.get("body") or ""):
                comment_id = comment.get("id")
                if isinstance(comment_id, int):
                    patched = requests.patch(
                        f"https://api.github.com/repos/{repo}/pulls/comments/{comment_id}",
                        headers=headers,
                        json={"body": body},
                        timeout=30,
                    )
                    return patched.status_code == 200

    created = requests.post(
        list_url,
        headers=headers,
        json={
            "body": body,
            "commit_id": commit_id,
            "path": anchor["path"],
            "line": anchor["line"],
            "side": "RIGHT",
        },
        timeout=30,
    )
    return created.status_code == 201
