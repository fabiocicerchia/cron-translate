# Architecture

## Overview

cron-translate is a single-module CLI (`cron_translate.py`). It parses a cron
expression, renders a plain-language description, and computes upcoming run
times in a target timezone, flagging DST transitions.

## Components

- **Parser / describer** — turns a cron expression into human-readable text.
- **Scheduler** — computes the next N run times (via `croniter`).
- **DST check** — compares consecutive runs across timezone offset changes and
  warns when a run may be skipped (spring forward) or duplicated (fall back).

## Data flow

expression → validate → describe → next-runs (tz-aware) → DST warnings → stdout

## Decisions

Record significant choices here (or in a `docs/adr/` folder if they pile up).
