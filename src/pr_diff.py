import os
import re
from typing import Any

import requests


# Patches are additional prompt payload on top of the log sections, so the
# budget is deliberately modest.
MAX_DIFF_CHARS = 6000


def fetch_pr_files(
    repo: str,
    pr_number: int,
    headers: dict[str, Any],
) -> list[dict[str, Any]]:
    """Fetch the files changed by a pull request.

    Args:
        repo: Repository in format 'owner/repo'.
        pr_number: Pull request number.
        headers: GitHub API headers (with auth and Accept).

    Returns:
        List of file entries from the API, or an empty list if the
        request fails. Diff context is optional, so a failure here must
        not stop the analysis.
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files?per_page=100"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        return []
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def _mentions(text: str, name: str) -> bool:
    """Check whether text refers to this exact file, not a longer one.

    A plain substring test would match "inventory.py" inside
    "test_inventory.py" and pull in unrelated patches, so the match is
    bounded by characters that cannot appear mid-filename.

    Args:
        text: Log text to search.
        name: File path or basename to look for.

    Returns:
        True when the name appears as a complete filename.
    """
    pattern = rf"(?<![A-Za-z0-9_.\-]){re.escape(name)}(?![A-Za-z0-9_\-])"
    return re.search(pattern, text) is not None


def select_files_mentioned_in_log(
    files: list[dict[str, Any]],
    log_text: str,
    max_chars: int = MAX_DIFF_CHARS,
) -> list[dict[str, str]]:
    """Pick the changed files that the failing log actually mentions.

    Sending the whole diff would bury the error; sending only the files
    named in the log keeps the prompt focused on what broke. Full-path
    matches rank ahead of basename matches.

    Args:
        files: File entries from fetch_pr_files().
        log_text: Text of the failing log sections.
        max_chars: Combined budget for the selected patches.

    Returns:
        List of {'filename', 'patch'} dicts within the character budget.
    """
    ranked: list[tuple[int, str, str]] = []
    for entry in files:
        path = entry.get("filename") or ""
        patch = entry.get("patch") or ""
        # Binary files and very large diffs come back without a patch.
        if not path or not patch:
            continue
        if _mentions(log_text, path):
            rank = 0
        elif _mentions(log_text, os.path.basename(path)):
            rank = 1
        else:
            continue
        ranked.append((rank, path, patch))

    ranked.sort(key=lambda item: (item[0], item[1]))

    selected: list[dict[str, str]] = []
    used = 0
    for _, path, patch in ranked:
        if used + len(patch) > max_chars:
            continue
        selected.append({"filename": path, "patch": patch})
        used += len(patch)
    return selected


def build_diff_section(selected: list[dict[str, str]]) -> str:
    """Render selected patches as a single prompt section.

    Args:
        selected: Output of select_files_mentioned_in_log().

    Returns:
        Formatted patch text, or an empty string when nothing was selected.
    """
    return "\n\n".join(
        f"--- {item['filename']}\n{item['patch']}" for item in selected
    )
