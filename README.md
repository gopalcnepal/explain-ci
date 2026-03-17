# explain-ci

Explain failed GitHub Actions jobs in plain English using your own LLM key.

This action:
- reads the failed job log from the current workflow run,
- extracts key error sections,
- asks your selected OpenAI-compatible model for a concise explanation,
- posts the result to PR when PR exists, otherwise to the commit.

## Requirements

- **IMPORTANT: explain-ci must run as a separate job** that depends on the job(s) being analyzed (see job placement below).
- A valid API key for your chosen provider.
- Workflow token permissions: `actions: read`, `contents: write`, `pull-requests: write`.

Recommended workflow permissions:

```yaml
permissions:
	actions: read
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

## Usage: Job Placement

⚠️ **CRITICAL**: explain-ci must run as a **separate job** (not a step in the failing job). This ensures:
- The failed job's log is finalized and queryable via GitHub API
- Multiple failed jobs in the same workflow are handled correctly
- The action can run with appropriate timeout and error handling

## Quickstart: Separate Job Pattern

Place explain-ci in its own job that depends on other jobs:

```yaml
name: CI

on:
	pull_request:
	push:

permissions:
	actions: read
	contents: write
	pull-requests: write

jobs:
	test:
		runs-on: ubuntu-latest
		steps:
			- uses: actions/checkout@v5

			- name: Run tests
				run: |
					npm test

	explain-failure:
		if: always()
		needs: test
		runs-on: ubuntu-latest
		steps:
			- name: Explain CI failure
				uses: gopalcnepal/explain-ci@v1
				with:
					api_key: ${{ secrets.OPENAI_API_KEY }}
```

Key points:
- `explain-failure` job has `needs: test` (depends on the test job)
- Uses `if: always()` so it runs whether test passed or failed
- Placed **after** all jobs you want to analyze
- explain-ci will detect failures from any job in the workflow

## Provider Examples

### OpenAI

```yaml
explain-failure:
	if: always()
	needs: [test, lint]
	runs-on: ubuntu-latest
	steps:
		- name: Explain CI failure
			uses: gopalcnepal/explain-ci@v1
			with:
				api_key: ${{ secrets.OPENAI_API_KEY }}
				provider: openai
				model: gpt-4o-mini
```

### Claude

```yaml
explain-failure:
	if: always()
	needs: [test, lint]
	runs-on: ubuntu-latest
	steps:
		- name: Explain CI failure
			uses: gopalcnepal/explain-ci@v1
			with:
				api_key: ${{ secrets.CLAUDE_API_KEY }}
				provider: claude
				model: claude-sonnet-4-6
```

### Gemini

```yaml
explain-failure:
	if: always()
	needs: [test, lint]
	runs-on: ubuntu-latest
	steps:
		- name: Explain CI failure
			uses: gopalcnepal/explain-ci@v1
			with:
				api_key: ${{ secrets.GEMINI_API_KEY }}
				provider: gemini
				model: gemini-2.0-flash
```

### Custom Endpoint (Ollama, Self-hosted, Azure)

```yaml
explain-failure:
	if: always()
	needs: [test, lint]
	runs-on: ubuntu-latest
	steps:
		- name: Explain CI failure
			uses: gopalcnepal/explain-ci@v1
			with:
				api_key: ${{ secrets.CUSTOM_LLM_API_KEY }}
				model: my-model
				base_url: https://my-endpoint.example.com/v1
```

## Behavior Notes

- **PR Comment Deduplication**: If the same commit is tested in both a `pull_request` event (PR) and a `push` event, only the PR run comments to avoid duplicates.
- **Comment Target**: If a PR exists for the commit, explains comment on the PR. Otherwise, comments on the commit directly.
- **Stale Run Protection**: Only the latest workflow run on a branch+event pair comments, preventing duplicate explanations from reruns.

## Self-hosted Runner Notes

- Ensure Python 3.12 is available or installable by `actions/setup-python@v5`.
- Ensure outbound network access to:
	- `api.github.com`
	- your selected LLM endpoint

## Private Repo and Fork Caveats

- PR comment posting requires `pull-requests: write`.
- For pull requests from forks, `GITHUB_TOKEN` is often read-only by default.
- If comments are not posted on fork PRs, this is usually a repository/org security policy and not an action bug.

## Using Action Outputs

You can reference explain-ci outputs in subsequent steps of the same job:

```yaml
explain-failure:
	if: always()
	needs: test
	runs-on: ubuntu-latest
	steps:
		- name: Explain CI failure
			id: explain
			uses: gopalcnepal/explain-ci@v1
			with:
				api_key: ${{ secrets.OPENAI_API_KEY }}

		- name: Log explanation outcome
			if: always()
			run: |
				echo "Explanation: ${{ steps.explain.outputs.explanation_markdown }}"
				echo "Posted to: ${{ steps.explain.outputs.comment_target }}"
				echo "PR Number: ${{ steps.explain.outputs.pr_number }}"
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