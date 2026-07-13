# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repo.

## Project

cron-translate is a small, self-contained Python 3.10+ CLI that converts cron
expressions to plain language and timezone-aware next-run times, with DST
warnings. The tool lives in `cron_translate.py` (entry point
`cron_translate:main`); tests live in `tests/`.

## Commands

```sh
# setup: make dev      # editable install with dev deps (pytest, ruff, build)
# test:  make test     # pytest -q
# lint:  make lint     # ruff check .
# build: make build    # python -m build
# run:   cron-translate '*/15 9-17 * * 1-5'
```

## Conventions

- Match existing style; don't reformat unrelated code.
- Use Conventional Commit messages; don't edit CHANGELOG.md by hand (release-please generates it).
- Update docs/ and examples/ with behavior changes.
- Never commit secrets; CI runs gitleaks. Keep `.env` out of git.

## Guardrails

- Don't add dependencies without a clear reason; prefer stdlib.
- Don't touch generated files (`*.egg-info/`, `dist/`) by hand.
- Ask before large refactors or destructive operations.
