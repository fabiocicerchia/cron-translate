# cron-translate

[![CI](https://github.com/fabiocicerchia/cron-translate/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiocicerchia/cron-translate/actions/workflows/ci.yml)
[![Security](https://github.com/fabiocicerchia/cron-translate/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/cron-translate/actions/workflows/security.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/cron-translate/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/cron-translate)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Ffabiocicerchia%2Fcron-translate.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Ffabiocicerchia%2Fcron-translate?ref=badge_shield)
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

## Development

`make setup` (git hooks + pre-commit), then `make dev` and `make test` / `make lint`.

## Documentation

Full docs live in [`docs/`](docs/). Runnable examples live in [`examples/`](examples/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a public issue.

## License

Apache 2.0 — see [LICENSE](LICENSE).
