# AI CI Error Explainer

Explain failed GitHub Actions jobs in plain English using your own LLM key.

This action:
- reads the failed job log from the current workflow run,
- extracts key error sections,
- asks your selected OpenAI-compatible model for a concise explanation,
- posts the result to PR when PR exists, otherwise to the commit.

## Requirements

- A workflow job that can run this action when previous steps fail (`if: failure()`).
- A valid API key for your chosen provider.
- Workflow token permissions that allow PR comments.

Recommended workflow permissions:

```yaml
permissions:
	contents: write
	pull-requests: write
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `api_key` | Yes | - | API key for OpenAI-compatible provider |
| `model` | No | `gpt-4o-mini` | Model name |
| `provider` | No | `openai` | Provider shorthand (`openai`, `claude`, `gemini`, `openrouter`, etc.) |
| `base_url` | No | `""` | Custom OpenAI-compatible endpoint; overrides provider mapping |

## Outputs

| Output | Description |
|---|---|
| `explanation_markdown` | LLM explanation markdown |
| `comment_target` | `pr`, `commit`, `none`, `stale_skipped`, or `*_post_failed` |
| `comment_posted` | `true` or `false` |
| `pr_number` | Resolved PR number if available |

## Quickstart (Basic)

```yaml
name: CI

on:
	pull_request:
	push:

permissions:
	contents: write
	pull-requests: write

jobs:
	test:
		runs-on: ubuntu-latest
		steps:
			- uses: actions/checkout@v5

			- name: Run tests
				run: |
					echo "simulate failure"
					exit 1

			- name: Explain failure
				if: failure()
				uses: gopalcnepal/ai-ci-error-explainer@v1
				with:
					api_key: ${{ secrets.OPENAI_API_KEY }}
```

## Provider Switch Examples

OpenAI:

```yaml
- name: Explain failure (OpenAI)
	if: failure()
	uses: gopalcnepal/ai-ci-error-explainer@v1
	with:
		api_key: ${{ secrets.OPENAI_API_KEY }}
		provider: openai
		model: gpt-4o-mini
```

Claude:

```yaml
- name: Explain failure (Claude)
	if: failure()
	uses: gopalcnepal/ai-ci-error-explainer@v1
	with:
		api_key: ${{ secrets.CLAUDE_API_KEY }}
		provider: claude
		model: claude-sonnet-4-6
```

Gemini (OpenAI-compatible endpoint):

```yaml
- name: Explain failure (Gemini)
	if: failure()
	uses: gopalcnepal/ai-ci-error-explainer@v1
	with:
		api_key: ${{ secrets.GEMINI_API_KEY }}
		provider: gemini
		model: gemini-2.0-flash
```

OpenRouter:

```yaml
- name: Explain failure (OpenRouter)
	if: failure()
	uses: gopalcnepal/ai-ci-error-explainer@v1
	with:
		api_key: ${{ secrets.OPENROUTER_API_KEY }}
		provider: openrouter
		model: openai/gpt-4o-mini
```

## Custom base_url Example

```yaml
- name: Explain failure (Custom Endpoint)
	if: failure()
	uses: gopalcnepal/ai-ci-error-explainer@v1
	with:
		api_key: ${{ secrets.CUSTOM_LLM_API_KEY }}
		model: my-model
		base_url: https://my-endpoint.example.com/v1
```

## Behavior Notes

- If a PR exists for the run commit, the action comments on the PR only.
- If no PR exists, the action comments on the run head commit.
- To avoid stale comments on older runs, only the latest run for that branch/event posts a comment.

## Self-hosted Runner Notes

- Ensure Python 3.12 is available or installable by `actions/setup-python@v5`.
- Ensure outbound network access to:
	- `api.github.com`
	- your selected LLM endpoint

## Private Repo and Fork Caveats

- PR comment posting requires `pull-requests: write`.
- For pull requests from forks, `GITHUB_TOKEN` is often read-only by default.
- If comments are not posted on fork PRs, this is usually a repository/org security policy and not an action bug.

## Reuse Outputs In Later Steps

```yaml
- name: Explain failure
	id: explain
	if: failure()
	uses: gopalcnepal/ai-ci-error-explainer@v1
	with:
		api_key: ${{ secrets.OPENAI_API_KEY }}

- name: Print explanation output
	if: always()
	run: |
		echo "target=${{ steps.explain.outputs.comment_target }}"
		echo "posted=${{ steps.explain.outputs.comment_posted }}"
		echo "pr=${{ steps.explain.outputs.pr_number }}"
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Missing required input: api_key` | Input not passed | Provide `with: api_key: ${{ secrets... }}` |
| No comment appears for older run | Stale run protection skipped it | Expected; newest run handles comment |
| `comment_target=pr_post_failed` | Token lacks write scope | Add `pull-requests: write` permissions |
| `comment_target=commit_post_failed` | Token lacks contents scope | Add `contents: write` permissions |
| 401/403 from provider API | Invalid key or endpoint | Verify key, provider, model, and `base_url` |
| Action not found or wrong version | Bad ref in `uses` | Use stable tag (for example `@v1`) |

## Development

- Runtime dependencies are listed in `requirements.txt`.
- Entrypoint is `main.py` at the repository root.
- Core implementation follows flow-based modules under `src/`:
  - `config.py` - Configuration and environment variable loading
  - `fetch_logs.py` - GitHub API integration for log retrieval
  - `parse_logs.py` - Log parsing and error section extraction
  - `llm_analysis.py` - LLM integration and response formatting
  - `post_comment.py` - PR and commit comment posting logic
- All code is documented with docstrings following Google-style format.
- Type hints are present throughout for IDE support and type checking.