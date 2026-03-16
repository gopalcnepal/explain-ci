import os
from typing import Any


PROVIDER_BASE_URLS = {
    "openai": None,
    "claude": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "grok": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
}


def get_runtime_config() -> dict[str, Any]:
    """Load runtime configuration from environment variables.

    Reads GitHub Actions injected variables (GITHUB_*) and custom inputs
    (INPUT_*). Provides sensible defaults for optional settings.

    Returns:
        Dictionary with keys: api_key, model, provider, base_url,
        github_token, repo, run_id, event_name, sha, pr_number,
        default_log_length.
    """
    provider = os.environ.get("INPUT_PROVIDER", "openai").strip().lower()
    custom_base_url = os.environ.get("INPUT_BASE_URL", "").strip()

    return {
        "api_key": os.environ.get("INPUT_API_KEY", "").strip(),
        "model": os.environ.get("INPUT_MODEL", "gpt-4o-mini").strip(),
        "provider": provider,
        "base_url": custom_base_url or PROVIDER_BASE_URLS.get(provider),
        "github_token": os.environ.get("GITHUB_TOKEN", "").strip(),
        "repo": os.environ.get("GITHUB_REPOSITORY", "").strip(),
        "run_id": os.environ.get("GITHUB_RUN_ID", "").strip(),
        "event_name": os.environ.get("GITHUB_EVENT_NAME", "").strip(),
        "sha": os.environ.get("GITHUB_SHA", "").strip(),
        "pr_number": os.environ.get("PR_NUMBER", "").strip(),
        "default_log_length": int(os.environ.get("DEFAULT_LOG_LENGTH", "1000")),
    }