import requests
from typing import Any

def get_workflow_failure_data(
    repo: str,
    run_id: str,
    github_token: str,
) -> dict[str, Any]:
    """Fetch failure data from GitHub API.

    Detects stale runs (when newer run exists on same branch/event)
    to prevent commenting on outdated commits.

    Args:
        repo: Repository in format 'owner/repo'.
        run_id: Workflow run ID to fetch.
        github_token: GitHub API authentication token.

    Returns:
        Dictionary with keys:
        - status: 'ok', 'stale_run', 'no_failed_job', or 'invalid_job_id'
        - run_data: Full run JSON from GitHub API
        - headers: API headers for subsequent requests
        - raw_log: (if status='ok') Raw job log text
    """
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    run_resp = requests.get(run_url, headers=headers, timeout=30)
    run_resp.raise_for_status()
    run_data = run_resp.json()

    # Skip stale runs: only the newest run on the same branch+event should comment.
    branch = run_data.get("head_branch")
    event = run_data.get("event")
    current_run_id = int(run_data.get("id") or 0)
    commit_sha = run_data.get("head_sha", "").strip()
    
    if branch and event and current_run_id:
        latest_url = (
            f"https://api.github.com/repos/{repo}/actions/runs"
            f"?branch={branch}&event={event}&per_page=1"
        )
        latest_resp = requests.get(latest_url, headers=headers, timeout=30)
        latest_resp.raise_for_status()
        latest_runs = latest_resp.json().get("workflow_runs", [])
        if latest_runs:
            latest_run_id = int(latest_runs[0].get("id") or 0)
            if latest_run_id and latest_run_id != current_run_id:
                return {
                    "status": "stale_run",
                    "run_data": run_data,
                    "headers": headers,
                }
    
    # For push events: if PR exists for this commit, skip this run.
    # (The pull_request event run will handle the comment to avoid duplicates)
    if event == "push" and commit_sha:
        pr_search_url = (
            f"https://api.github.com/repos/{repo}/commits/{commit_sha}/pulls"
            f"?state=open&per_page=1"
        )
        pr_search_resp = requests.get(pr_search_url, headers=headers, timeout=30)
        if pr_search_resp.status_code == 200:
            open_prs = pr_search_resp.json()
            if open_prs and isinstance(open_prs, list) and len(open_prs) > 0:
                return {
                    "status": "stale_run",
                    "run_data": run_data,
                    "headers": headers,
                }


    jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    jobs_resp = requests.get(jobs_url, headers=headers, timeout=30)
    jobs_resp.raise_for_status()

    failed_job = None
    for job in jobs_resp.json().get("jobs", []):
        # Look for jobs with conclusion=failure (completed) or with failed steps (in_progress)
        if job.get("conclusion") == "failure":
            failed_job = job
            break
        # Check for jobs with at least one failed step (current job may still be in_progress)
        steps = job.get("steps", [])
        if steps and any(step.get("conclusion") == "failure" for step in steps):
            failed_job = job
            break

    if not failed_job:
        return {"status": "no_failed_job", "run_data": run_data, "headers": headers}

    job_id = failed_job.get("id")
    if not isinstance(job_id, int):
        return {"status": "invalid_job_id", "run_data": run_data, "headers": headers}

    log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    log_resp = requests.get(log_url, headers=headers, timeout=60)
    log_resp.raise_for_status()

    return {
        "status": "ok",
        "run_data": run_data,
        "headers": headers,
        "raw_log": log_resp.text,
    }