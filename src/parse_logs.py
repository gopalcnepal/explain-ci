import re
from typing import Any


def parse_log_sections(
    raw_log: str,
    default_log_length: int | None = None,
) -> dict[str, str]:
    """Parse error sections from raw GitHub Actions logs.

    Attempts to extract structured sections using GitHub log markers
    (##[group], ##[endgroup], ##[error]). Falls back to last N lines
    if markers not found.

    Args:
        raw_log: Raw job log text from GitHub API.
        default_log_length: Number of lines to use in fallback.

    Returns:
        Dictionary with keys:
        - step_context: Step that was running (from ##[group])
        - actual_error: Error output between step and ##[error]
        - github_error: Runner status from ##[error] onward
    """
    if default_log_length is None:
        default_log_length = 1000
    cleaned = re.sub(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s",
        "",
        raw_log,
        flags=re.MULTILINE,
    )
    lines = cleaned.split("\n")

    error_idx = -1
    for i, line in enumerate(lines):
        if "##[error]" in line:
            error_idx = i
            break

    if error_idx == -1:
        fallback_lines = lines[-default_log_length:]
        return {
            "step_context": "No formal group block detected.",
            "actual_error": (
                "No explicit ##[error] tag found. Providing the last "
                f"{default_log_length} lines of execution."
            ),
            "github_error": "\n".join(fallback_lines).strip(),
        }

    endgroup_idx = 0
    for i in range(error_idx, -1, -1):
        if "##[endgroup]" in lines[i]:
            endgroup_idx = i
            break

    group_idx = 0
    for i in range(endgroup_idx, -1, -1):
        if "##[group]" in lines[i]:
            group_idx = i
            break

    cleanup_idx = len(lines)
    for i in range(error_idx, len(lines)):
        if "Post job cleanup" in lines[i]:
            cleanup_idx = i
            break

    return {
        "step_context": "\n".join(lines[group_idx : endgroup_idx + 1]).strip(),
        "actual_error": "\n".join(lines[endgroup_idx + 1 : error_idx]).strip(),
        "github_error": "\n".join(lines[error_idx:cleanup_idx]).strip(),
    }