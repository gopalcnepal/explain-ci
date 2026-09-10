import requests
from typing import Any


COMMENT_MARKER = "<!-- explain-ci -->"


def _find_marker_comment_id(list_url: str, headers: dict[str, Any]) -> int | None:
    """Find an existing explain-ci comment by its hidden marker.

    Args:
        list_url: GitHub API URL that lists comments for a PR or commit.
        headers: GitHub API headers (with auth and Accept).

    Returns:
        Comment id when a comment containing COMMENT_MARKER exists,
        otherwise None (including on listing errors).
    """
    resp = requests.get(f"{list_url}?per_page=100", headers=headers, timeout=30)
    if resp.status_code != 200:
        return None
    for comment in resp.json():
        if COMMENT_MARKER in (comment.get("body") or ""):
            comment_id = comment.get("id")
            if isinstance(comment_id, int):
                return comment_id
    return None


def _upsert_comment(
    list_url: str,
    edit_url_base: str,
    headers: dict[str, Any],
    body: str,
) -> bool:
    """Create the explain-ci comment, or update it when one exists.

    Keeps re-runs from stacking duplicate comments: the existing
    marker comment is PATCHed in place instead of POSTing a new one.

    Args:
        list_url: URL that lists (and creates) comments for the target.
        edit_url_base: URL prefix for editing a comment by id.
        headers: GitHub API headers (with auth and Accept).
        body: Full comment body including COMMENT_MARKER.

    Returns:
        True when the comment was created or updated successfully.
    """
    existing_id = _find_marker_comment_id(list_url, headers)
    if existing_id is not None:
        resp = requests.patch(
            f"{edit_url_base}/{existing_id}",
            headers=headers,
            json={"body": body},
            timeout=30,
        )
        return resp.status_code == 200
    resp = requests.post(list_url, headers=headers, json={"body": body}, timeout=30)
    return resp.status_code == 201


def resolve_pr_number(
    explicit_pr_number: str,
    run_data: dict[str, Any],
) -> int | None:
    """Work out which PR this run belongs to, if any.

    Args:
        explicit_pr_number: PR number from the event payload, '' if absent.
        run_data: Workflow run data from get_workflow_failure_data().

    Returns:
        The PR number, or None when the run has no associated PR.
    """
    if explicit_pr_number.strip().isdigit():
        return int(explicit_pr_number.strip())
    pull_requests = run_data.get("pull_requests") or []
    if pull_requests and isinstance(pull_requests[0].get("number"), int):
        return int(pull_requests[0]["number"])
    return None


def publish_comment(
    repo: str,
    headers: dict[str, Any],
    run_data: dict[str, Any],
    explicit_pr_number: str,
    markdown_body: str,
) -> dict[str, str]:
    """Post explanation comment to PR or commit.

    Routes comment based on PR availability and validates staleness.
    Comments carry a hidden marker so re-runs update the existing
    explain-ci comment instead of posting a duplicate.

    Args:
        repo: Repository in format 'owner/repo'.
        headers: GitHub API headers (with auth and Accept).
        run_data: Workflow run data from get_workflow_failure_data().
        explicit_pr_number: PR number if known (empty string if not).
        markdown_body: Explanation text to post.

    Returns:
        Dictionary with keys:
        - comment_target: 'pr', 'commit', 'none', 'stale_skipped', or '*_post_failed'
        - comment_posted: 'true' or 'false'
        - pr_number: PR number if applicable, empty otherwise
    """
    body = f"{COMMENT_MARKER}\n{markdown_body}"

    run_head_sha = (run_data.get("head_sha") or "").strip()
    if not run_head_sha:
        return {
            "comment_target": "none",
            "comment_posted": "false",
            "pr_number": "",
        }

    pr_number = resolve_pr_number(explicit_pr_number, run_data)

    if pr_number:
        # PR exists: comment only on PR and never on commit to avoid duplicates.
        pr_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        pr_resp = requests.get(pr_url, headers=headers, timeout=30)
        pr_resp.raise_for_status()
        pr_data = pr_resp.json()
        current_pr_head = ((pr_data.get("head") or {}).get("sha") or "").strip()

        # Avoid stale comment from older runs.
        if current_pr_head != run_head_sha:
            return {
                "comment_target": "stale_skipped",
                "comment_posted": "false",
                "pr_number": str(pr_number),
            }

        posted = _upsert_comment(
            f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
            f"https://api.github.com/repos/{repo}/issues/comments",
            headers,
            body,
        )
        return {
            "comment_target": "pr" if posted else "pr_post_failed",
            "comment_posted": "true" if posted else "false",
            "pr_number": str(pr_number),
        }

    # No PR associated: comment on the run head commit.
    posted = _upsert_comment(
        f"https://api.github.com/repos/{repo}/commits/{run_head_sha}/comments",
        f"https://api.github.com/repos/{repo}/comments",
        headers,
        body,
    )
    return {
        "comment_target": "commit" if posted else "commit_post_failed",
        "comment_posted": "true" if posted else "false",
        "pr_number": "",
    }