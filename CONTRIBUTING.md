# Contributing

Thanks for taking the time to contribute to cron-translate!

## Development setup

You need Python 3.10+ and `make`.

```sh
make setup   # install git hooks (gitleaks) and pre-commit
make dev     # editable install with dev dependencies (pytest, ruff, build)
make lint    # ruff check .
make test    # pytest
```

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`,
`fix:`, `docs:`, `chore:`, etc. This drives the version bump (`fix:` → patch,
`feat:` → minor, `feat!:`/`BREAKING CHANGE:` → major) and the changelog.

## Pull requests

1. Fork and create a topic branch.
1. Make your change, keeping the existing style; add or update tests.
1. Make sure `make lint` and `make test` pass locally.
1. Open a PR with a clear description of the problem and the solution.

Don't edit `CHANGELOG.md` by hand — it's generated from commit messages by
release-please.

## Releases

Releases are automated by [release-please](.github/workflows/release.yml).
Merging `feat:`/`fix:` PRs into `main` doesn't release; release-please keeps an
open "chore: release X.Y.Z" PR with the next version bump and changelog.
Merging **that** PR tags `vX.Y.Z`, publishes the GitHub Release, builds the
package, and (when enabled) publishes to PyPI.

## License

By contributing you agree that your contributions are licensed under the
Apache License 2.0 (see `LICENSE`).
