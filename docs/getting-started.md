# Getting Started

## Prerequisites

- Python 3.10 or newer.

## Setup

```sh
pipx install .        # or: pip install .
```

## Run

```sh
cron-translate '*/15 9-17 * * 1-5'
cron-translate '30 2 * * *' --tz America/New_York --next 3
```

Say it in English instead, and it will tell you where cron cannot follow:

```sh
cron-translate 'every weekday at 9am'
cron-translate 'every 2 weeks'          # exits 64 and explains why
```

## Convert between dialects

```sh
cron-translate convert --from quartz --to eventbridge '0 0 12 ? * MON-FRI *'
cron-translate convert --from vixie --to systemd '0 9 * * 1-5'
```

Each conversion prints both expressions, one description, the next runs of
both on the same clock, and a caveat for anything the target reads
differently. A conversion the target cannot express exits `65` rather than
printing a wrong answer. See [Dialects](dialects.md) for the per-field rules.

## Exit codes

`0` OK, `64` the expression could not be read, `65` it was read and cannot be
honestly converted — handy for validating crontabs in CI:
`cron-translate "$SCHEDULE" >/dev/null`.
