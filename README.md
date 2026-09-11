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
cron-translate EXPRESSION [--tz IANA_TZ] [--next N] [--no-dst-check] [--between START END] [--json]
cron-translate convert --from DIALECT --to DIALECT EXPRESSION [--tz IANA_TZ] [--next N] [--json]
```

Exit codes: `0` OK, `64` the expression could not be read, `65` it was read
fine and cannot be honestly converted. Safe to use in CI to validate crontabs:
`cron-translate "$SCHEDULE" >/dev/null`.

## Where the words come from

The English description is [cron-descriptor][cron-descriptor]
(`Salamek/cron-descriptor`) — not a sentence builder of our own. It already
knows `L`, `W`, `#`, seconds, years and a dozen languages, and it has had far
more people argue with its phrasing than this repository ever will. Next-run
times are [croniter][croniter]. What is ours is the part no library does:
English → cron, the dialect converter, and the DST check.

### English → cron, and where cron gives up

Going this direction is guesswork dressed as a feature unless the tool admits
what cron cannot say — so it does, and exits non-zero rather than hand back
something that looks right:

```console
$ cron-translate 'every weekday at 9am'
0 9 * * 1-5
  → At 09:00, Monday through Friday
  ...

$ cron-translate 'every 2 weeks'; echo "exit $?"
cron-translate: cron has no week counter: the day-of-week field repeats every
week, so `every 2 weeks` cannot be written. Closest: run weekly with
`0 0 * * 0` and let the job decide (`[ $(( $(date +%V) % 2 )) -eq 0 ] || exit 0`),
or use a systemd timer with `OnUnitActiveSec=2w`.
exit 64
```

The same for `last friday of the month` (vixie has no `#` or `L`; Quartz does,
and it hands you `0 0 0 ? * 6L *`), `last day of the month`, and
`every 90 minutes` (the minute field stops at 59 — it prints the two crontab
lines that between them do it). Phrases that *are* expressible but come with a
cron gotcha are translated and flagged: `every 7 minutes` works, with a note
that `*/7` restarts at the top of every hour, so the gap across `:00` is four
minutes rather than seven.

## Dialects

`convert` moves one schedule between five dialects, and refuses rather than
guess:

| Dialect | `--from` / `--to` | Fields | What is particular to it |
|---|---|---|---|
| vixie cron | `vixie`, `cron`, `crontab`, `unix` | 5 | day-of-week 0-6, with 7 also Sunday; `@daily` and friends |
| Kubernetes CronJob | `k8s`, `kubernetes`, `cronjob` | 5 | robfig/cron v3: day-of-week 0-6 only, no `L`, `W`, `?` or `#`; the zone is `spec.timeZone`, not the expression |
| AWS EventBridge | `eventbridge`, `aws` | 6 | year field, no seconds, day-of-week 1-7 with **1 = Sunday**, exactly one day field must be `?`, no `/` in day-of-week, one `#` term at most |
| Quartz | `quartz` | 6-7 | leading seconds, optional year (stops at 2099), day-of-week 1-7, and the full `L` / `L-n` / `LW` / `nW` / `nL` / `n#m` vocabulary |
| systemd | `systemd`, `oncalendar`, `timer` | — | `DOW Y-M-D H:M:S [TZ]`; `~n` counts back from the end of the month; the weekday is **ANDed** with the date |

```console
$ cron-translate convert --from quartz --to eventbridge '0 0 12 ? * MON-FRI *'
quartz       0 0 12 ? * MON-FRI *
eventbridge  0 12 ? * 2-6 *

  → At 12:00, Monday through Friday

Next 3 runs (UTC), both dialects on the same clock:
  quartz               eventbridge
  2026-09-11 12:00:00  2026-09-11 12:00:00
  2026-09-14 12:00:00  2026-09-14 12:00:00
  2026-09-15 12:00:00  2026-09-15 12:00:00
```

Those two run columns are a check, not a restatement: the converted text is
parsed back with the *target* dialect's own parser and scheduled
independently. If the columns ever disagree, that is a bug and the tool says
so and exits non-zero.

### The caveats it will tell you about

- **Seconds.** Quartz and systemd have them; vixie, Kubernetes and EventBridge
  do not. `30 0 12 ? * MON-FRI *` → vixie is exit 65, with `0 12 * * 1-5`
  offered as the closest expression and labelled *not equivalent*.
- **day-of-month vs day-of-week.** Cron fires when **either** matches once both
  are restricted. EventBridge and Quartz cannot write that at all — they
  require `?` in exactly one of the two — and systemd means **and**, not
  **or**. All three directions are refused rather than silently re-read.
- **`?` becomes `*`.** Going the other way is lossless but worth saying, so a
  caveat says it.
- **`L`, `W`, `#`.** Quartz says all of them; EventBridge takes `L` and `W` and
  `#` but not `L-n` or `LW`; systemd writes "last day" as `~01` and has no
  nearest-weekday or nth-weekday syntax at all; vixie and Kubernetes have none
  of it.
- **Years.** EventBridge reaches 2199 and Quartz stops at 2099; vixie and
  Kubernetes have no year field, so a year-limited schedule will not convert.
- **Timezones.** Each dialect keeps the zone somewhere else — `CRON_TZ=` above
  the entry, `spec.timeZone` on the CronJob, the Quartz trigger, a suffix on
  `OnCalendar=` — so the caveat names the right place instead of inventing a
  field.

`docs/dialects.md` has the full per-field tables.

## Daylight saving

With `--tz`, each run that a transition touches is flagged where it is
printed — not just "a transition is coming":

```console
$ cron-translate '30 2 * * *' --tz America/New_York \
    --between 2027-03-13T00:00 2027-03-15T00:00
...
  2027-03-13 02:30 EST
  2027-03-14 03:00 EDT  ⚠ DST: this wall-clock time does not exist (spring
                          forward) — the run is skipped or shifted
```

Fall back is flagged the same way, on both copies of the repeated hour.
`--no-dst-check` turns it off.

[cron-descriptor]: https://github.com/Salamek/cron-descriptor
[croniter]: https://github.com/kiorky/croniter

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
