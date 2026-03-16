# Contributing to AI CI Error Explainer

Thank you for your interest in contributing! This document outlines our standards and practices.

## Code Standards

### Python Code Style
- **PEP 8**: All Python code must follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- **Block length**: Maximum 99 characters per line
- **Docstrings**: All modules, classes, and functions must have docstrings (Google-style format)
- **Type hints**: Use full type annotations on all function signatures
- **Imports**: Sort imports alphabetically, standard library first, then third-party, then local

### Git Practices
- **Branch naming**: Use descriptive names (e.g., `feature/add-claude-support`, `fix/stale-run-detection`)
- **Commit messages**: Start with verb (Add, Fix, Update, Remove)
- **PRs**: Include description of what changed and why
- **No force push**: Especially on shared branches

### GitHub Actions Best Practices
- Always pin external action versions (e.g., `actions/checkout@v4.0.0`)
- Use `::notice::`, `::group::`, `::error::` commands for structured output
- Mask secrets with `::add-mask::`
- Include `shell: bash` on all run steps
- Document required permissions in action.yml

## Before Submitting

1. **Run tests**: `python -m pytest` (when test suite exists)
2. **Check style**: Files must follow PEP 8
3. **Lint**: Use `pylint` or `flake8` (optional for this project)
4. **Verify action**: Test with real failing workflow if possible

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Reporting Issues

Include:
- GitHub Actions log output (masked if they contain secrets)
- LLM provider being used (OpenAI, Gemini, etc.)
- Steps to reproduce
- Expected vs actual behavior

## Security

- Never commit API keys or tokens to the repo
- Use GitHub Secrets for sensitive values
- Report security issues privately via GitHub Security Advisory
