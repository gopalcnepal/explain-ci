import os

from src.config import get_runtime_config
from src.fetch_logs import get_workflow_failure_data
from src.llm_analysis import build_explanation_markdown
from src.parse_logs import parse_log_sections
from src.post_comment import publish_comment


def gha_notice(message: str) -> None:
    """Print a GitHub Actions notice command.

    Args:
        message: Text to display as a workflow notice.
    """
    print(f"::notice::{message}")


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


def main() -> int:
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
            config["default_log_length"],
        )
        gha_notice("Log parsing completed")
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

    gha_group_start("Publish comment")
    try:
        publish_data = publish_comment(
            config["repo"],
            failure_data["headers"],
            failure_data["run_data"],
            config["pr_number"],
            markdown,
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


if __name__ == "__main__":
    raise SystemExit(main())