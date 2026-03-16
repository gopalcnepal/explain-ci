from openai import OpenAI
from typing import Any


def build_explanation_markdown(
    api_key: str,
    model: str,
    base_url: str | None,
    provider: str,
    parsed_data: dict[str, Any],
) -> str:
    """Generate markdown explanation from parsed error sections.

    Sends 3 log sections to LLM (via OpenAI SDK with optional custom
    base_url for other providers). Returns Markdown with Root Cause
    and Suggested Fix sections.

    Args:
        api_key: API key for LLM provider.
        model: Model identifier (e.g., 'gpt-4o-mini').
        base_url: Optional custom endpoint (overrides provider default).
        provider: Provider shorthand for footer attribution.
        parsed_data: Dictionary with step_context, actual_error, github_error.

    Returns:
        Markdown-formatted explanation with model/provider attribution.
    """
    client = OpenAI(api_key=api_key, base_url=base_url)

    system_prompt = (
        "You are an expert DevOps engineer analyzing failed GitHub Actions logs. "
        "Be concise and return Markdown with exactly two sections: "
        "**Root Cause:** and **Suggested Fix:**."
    )

    user_prompt = (
        "Analyze these extracted sections from a failed CI job:\n\n"
        "### 1. Context\n"
        "```text\n"
        f"{parsed_data.get('step_context', 'No context available')}\n"
        "```\n\n"
        "### 2. Actual Error\n"
        "```text\n"
        f"{parsed_data.get('actual_error', 'No specific error extracted')}\n"
        "```\n\n"
        "### 3. GitHub Runner Error\n"
        "```text\n"
        f"{parsed_data.get('github_error', 'No runner status available')}\n"
        "```"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
    )

    explanation = response.choices[0].message.content or "No explanation returned by model."
    return (
        "## AI CI Error Explanation\n\n"
        f"{explanation}\n\n"
        f"_Model: {model} | Provider: {provider}_"
    )