import requests
from typing import Any


def publish_comment(
    repo: str,
    headers: dict[str, Any],
    run_data: dict[str, Any],
    explicit_pr_number: str,
    markdown_body: str,
) -> dict[str, str]:
    """Post explanation comment to PR or commit.

    Routes comment based on PR availability and validates staleness.

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
    run_head_sha = (run_data.get("head_sha") or "").strip()
    if not run_head_sha:
        return {
            "comment_target": "none",
            "comment_posted": "false",
            "pr_number": "",
        }

    pr_number = None
    if explicit_pr_number.strip().isdigit():
        pr_number = int(explicit_pr_number.strip())
    else:
        pull_requests = run_data.get("pull_requests") or []
        if pull_requests and isinstance(pull_requests[0].get("number"), int):
            pr_number = int(pull_requests[0]["number"])

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

        comment_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
        comment_resp = requests.post(
            comment_url,
            headers=headers,
            json={"body": markdown_body},
            timeout=30,
        )
        return {
            "comment_target": "pr" if comment_resp.status_code == 201 else "pr_post_failed",
            "comment_posted": "true" if comment_resp.status_code == 201 else "false",
            "pr_number": str(pr_number),
        }

    # No PR associated: comment on the run head commit.
    commit_url = f"https://api.github.com/repos/{repo}/commits/{run_head_sha}/comments"
    commit_resp = requests.post(
        commit_url,
        headers=headers,
        json={"body": markdown_body},
        timeout=30,
    )
    return {
        "comment_target": "commit" if commit_resp.status_code == 201 else "commit_post_failed",
        "comment_posted": "true" if commit_resp.status_code == 201 else "false",
        "pr_number": "",
    }