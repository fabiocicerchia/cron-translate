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

Exit codes: `0` OK, `64` invalid expression — handy for validating crontabs in
CI: `cron-translate "$SCHEDULE" >/dev/null`.
