import os

from src.config import get_runtime_config
from src.fetch_logs import get_workflow_failure_data
from src.inline_comment import find_anchor, parse_error_locations
from src.llm_analysis import build_explanation_markdown
from src.parse_logs import parse_log_sections
from src.post_comment import publish_comment, resolve_pr_number
from src.pr_diff import build_diff_section, fetch_pr_files, select_files_mentioned_in_log
from src.redact import redact_sections


def gha_notice(message: str) -> None:
    """Print a GitHub Actions notice command.

    Args:
        message: Text to display as a workflow notice.
    """
    print(f"::notice::{message}")


def gha_warning(message: str) -> None:
    """Print a GitHub Actions warning command.

    Args:
        message: Text to display as a workflow warning.
    """
    print(f"::warning::{message}")


def gha_group_start(title: str) -> None:
    """Start a GitHub Actions log group.

    Args:
        title: Title for the log group.
    """
    print(f"::group::{title}")


def gha_group_end() -> None:
    """End the current GitHub Actions log group."""
    print("::endgroup::")


def mask_secret(value: str) -> None:
    """Mask a secret value in GitHub Actions logs.

    Args:
        value: Secret string to mask (e.g., API key).
    """
    if value:
        print(f"::add-mask::{value}")


def write_action_outputs(outputs: dict[str, str]) -> None:
    """Write action outputs to GITHUB_OUTPUT file.

    Handles multiline values using EOF markers per GitHub Actions spec.

    Args:
        outputs: Dictionary of key-value pairs to write as action outputs.
    """
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return

    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            text = str(value)
            if "\n" in text:
                handle.write(f"{key}<<EOF\n{text}\nEOF\n")
            else:
                handle.write(f"{key}={text}\n")


def run() -> int:
    """Main orchestration function.

    Coordinates all steps: fetch logs, parse, analyze with LLM,
    post comment, and write outputs.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    gha_notice("Starting AI CI Error Explainer")

    gha_group_start("Load configuration")
    try:
        config = get_runtime_config()
        # Mask secret as early as possible for this job.
        mask_secret(config["api_key"])
        gha_notice("Configuration loaded")
    finally:
        gha_group_end()

    gha_group_start("Validate required settings")
    try:
        if not config["api_key"]:
            raise RuntimeError("Missing required input: api_key")
        if not config["github_token"]:
            raise RuntimeError("Missing GITHUB_TOKEN")
        if not config["repo"] or not config["run_id"]:
            raise RuntimeError("Missing GitHub context (repository/run_id)")
        gha_notice("Required settings validated")
    finally:
        gha_group_end()

    gha_group_start("Fetch workflow failure data")
    try:
        failure_data = get_workflow_failure_data(
            config["repo"],
            config["run_id"],
            config["github_token"],
        )
        gha_notice(f"Failure data status: {failure_data['status']}")
    finally:
        gha_group_end()

    if failure_data["status"] == "stale_run":
        gha_notice("Detected stale run; skipping comment")
        write_action_outputs(
            {
                "explanation_markdown": "Skipped stale run to avoid commenting on outdated commits.",
                "comment_target": "stale_skipped",
                "comment_posted": "false",
                "pr_number": "",
            }
        )
        return 0

    if failure_data["status"] == "pr_run_exists":
        gha_notice("Open PR exists for this commit; the pull_request run will comment")
        write_action_outputs(
            {
                "explanation_markdown": "Skipped push run; the pull_request run comments instead.",
                "comment_target": "pr_run_exists",
                "comment_posted": "false",
                "pr_number": "",
            }
        )
        return 0

    if failure_data["status"] != "ok":
        gha_notice("No failed job found; skipping analysis")
        write_action_outputs(
            {
                "explanation_markdown": "No failed job found in this run.",
                "comment_target": "none",
                "comment_posted": "false",
                "pr_number": "",
            }
        )
        return 0

    gha_group_start("Parse logs")
    try:
        parsed_data = parse_log_sections(
            failure_data["raw_log"],
            config["log_lines"],
        )
        gha_notice("Log parsing completed")
    finally:
        gha_group_end()

    gha_group_start("Collect PR diff context")
    try:
        pr_number = resolve_pr_number(config["pr_number"], failure_data["run_data"])
        pr_files: list = []
        if pr_number:
            pr_files = fetch_pr_files(
                config["repo"], pr_number, failure_data["headers"]
            )
            parsed_data["pr_diff"] = build_diff_section(
                select_files_mentioned_in_log(
                    pr_files, "\n".join(parsed_data.values())
                )
            )
            gha_notice(
                "Diff context: "
                f"{len(parsed_data['pr_diff'])} chars from changed files named in the log"
            )
        else:
            gha_notice("No pull request for this run; skipping diff context")
    finally:
        gha_group_end()

    gha_group_start("Redact secrets")
    try:
        parsed_data, redaction_count = redact_sections(parsed_data)
        gha_notice(f"Redacted {redaction_count} credential-like value(s) before analysis")
    finally:
        gha_group_end()

    gha_group_start("Run LLM analysis")
    try:
        markdown = build_explanation_markdown(
            config["api_key"],
            config["model"],
            config["base_url"],
            config["provider"],
            parsed_data,
        )
        gha_notice("LLM analysis completed")
    finally:
        gha_group_end()

    gha_group_start("Locate failing line")
    try:
        anchor = find_anchor(
            parse_error_locations("\n".join(parsed_data.values())), pr_files
        )
        if anchor:
            gha_notice(f"Anchoring comment to {anchor['path']}:{anchor['line']}")
        else:
            gha_notice("No commentable line in the diff; using a normal comment")
    finally:
        gha_group_end()

    gha_group_start("Publish comment")
    try:
        publish_data = publish_comment(
            config["repo"],
            failure_data["headers"],
            failure_data["run_data"],
            config["pr_number"],
            markdown,
            anchor,
        )
        gha_notice(
            "Comment publish result: "
            f"target={publish_data['comment_target']}, "
            f"posted={publish_data['comment_posted']}"
        )
    finally:
        gha_group_end()

    gha_group_start("Write outputs")
    write_action_outputs(
        {
            "explanation_markdown": markdown,
            "comment_target": publish_data["comment_target"],
            "comment_posted": publish_data["comment_posted"],
            "pr_number": publish_data["pr_number"],
        }
    )
    gha_group_end()

    gha_notice("AI CI Error Explainer completed")
    return 0


def main() -> int:
    """Entry point that shields the caller's pipeline from failures.

    Any unexpected error becomes a ::warning:: plus safe outputs so the
    action never breaks CI. Set the fail_on_error input to 'true' to
    propagate a non-zero exit code instead.

    Returns:
        Exit code (0 unless an error occurred and fail_on_error is true).
    """
    try:
        return run()
    except Exception as exc:
        # Reads the env directly so this handler works even when
        # configuration loading is the step that failed.
        gha_warning(f"explain-ci failed: {exc}")
        write_action_outputs(
            {
                "explanation_markdown": f"explain-ci could not analyze this run: {exc}",
                "comment_target": "error",
                "comment_posted": "false",
                "pr_number": "",
            }
        )
        fail_on_error = (
            os.environ.get("INPUT_FAIL_ON_ERROR", "").strip().lower() == "true"
        )
        return 1 if fail_on_error else 0


if __name__ == "__main__":
    raise SystemExit(main())