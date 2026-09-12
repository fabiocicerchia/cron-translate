# cron-translate

[![CI](https://github.com/fabiocicerchia/cron-translate/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiocicerchia/cron-translate/actions/workflows/ci.yml)
[![Security](https://github.com/fabiocicerchia/cron-translate/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/cron-translate/actions/workflows/security.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/cron-translate/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/cron-translate)
[![CI carbon](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/fabiocicerchia/cron-translate/gh-pages/badge.json)](.github/workflows/carbon-badge.yml)
[![Release](https://img.shields.io/github/v/release/fabiocicerchia/cron-translate)](https://github.com/fabiocicerchia/cron-translate/releases)

Cron expressions ↔ plain language ↔ **timezone-aware next-run times**, with
**DST warnings**. Small, self-contained, pipeable.

Crontab guru in your terminal — plus the thing the web tools don't do: telling
you your 02:30 job silently won't run on the night the clocks jump.

```console
$ cron-translate '*/15 9-17 * * 1-5'
*/15 9-17 * * 1-5
  → every 15 minutes, during 9 through 17, on Monday through Friday

Next 3 runs (UTC):
  2026-07-10 14:15 UTC  (in 0.2h)
  ...

$ cron-translate '30 2 * * *' --tz America/New_York
...
⚠ DST transition between 2027-03-13 02:30 EST and 2027-03-14 03:30 EDT:
  a run may be skipped (spring forward) or duplicated (fall back)
```

## Features

- Translates a cron expression into **plain language**, so a review can catch
  a schedule that does not say what its author thought.
- Computes **timezone-aware next-run times** with `--tz` on any IANA zone,
  `--next N` for how many.
- **Warns on DST transitions** — the thing the web tools do not do: your 02:30
  job is silently skipped on spring-forward and run twice on fall-back.
- `--no-dst-check` when you have already accepted that risk.
- Usable as a crontab validator in CI: exit `0` on a valid expression, `64` on
  an invalid one.
- Small, self-contained and pipeable — no service, no config.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/cron-translate/main/install.sh | bash
```

Or with pipx directly:

```sh
pipx install .        # or: pip install .
```

## Usage

```text
cron-translate EXPRESSION [--tz IANA_TZ] [--next N] [--no-dst-check]
```

Exit codes: `0` OK, `64` invalid expression — safe to use in CI to validate
crontabs: `cron-translate "$SCHEDULE" >/dev/null`.

## Verifying the image

Every published image is signed with [cosign][cosign], keyless: the identity in
the signature is the workflow that published it, not a key anybody holds.

```sh
cosign verify ghcr.io/fabiocicerchia/cron-translate:latest \
  --certificate-identity-regexp \
    'https://github.com/fabiocicerchia/cron-translate/.github/workflows/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

`no signatures found` means the tag predates signing, not that verification was
set up wrongly — a wrong identity or issuer says so explicitly. Re-run the
publish workflow for that tag to sign it.

[cosign]: https://docs.sigstore.dev/

## Development

`make setup` (git hooks + pre-commit), then `make dev` and `make test` / `make lint`.

## Documentation

Full docs live in [`docs/`](docs/). Runnable examples live in [`examples/`](examples/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a public issue.

## Support

Need help implementing this? [Get in touch](https://fabiocicerchia.it/contact).

## License

Apache 2.0 — see [LICENSE](LICENSE).
