# Specifications of cron-translate

What this code does, one atomic Gherkin scenario per behaviour, read from the code by code-atlas.
Tags: `@verified` a test asserts it · `@inferred` read from the code only · `@gap` an entry point no test covers · `@human` written or amended by a person, never rewritten.

## Command-Line Experience
How users call the tool and read what it returns.

- **Error reporting and exit codes**: [Reporting errors and exit codes](command-line/errors/cli-errors.feature) (4)
- **JSON output**: [JSON output for scripts](command-line/json-output/json-output.feature) (3)

## Dialect Conversion
Reading schedules written for different schedulers and rewriting them for another.

- **Caveats and unconvertible schedules**: [Refusing or qualifying conversions that would change a schedule's meaning](dialect-conversion/caveats-and-limits/conversion-caveats-and-refusals.feature) (6)
- **Converting between dialects**: [Converting a schedule between cron dialects](dialect-conversion/convert/converting-between-dialects.feature) (4)
- **Proof runs**: [Proving a conversion with side-by-side runs](dialect-conversion/proof-runs/conversion-proof-runs-cron-translate.feature) (2), [Proving a conversion with side-by-side runs](dialect-conversion/proof-runs/conversion-proof-runs.feature) (1)
- **Supported dialects**: [Reading schedules in each dialect's syntax](dialect-conversion/supported-dialects/reading-dialect-syntax.feature) (4)

## Daylight Saving Safety
Warning users when clock changes make a schedule skip or repeat a run.

- **Turning off DST checks**: [Turning off DST checks](dst-safety/opt-out/dst-opt-out.feature) (1)
- **Per-run DST flags**: [Flagging runs in a skipped or repeated hour](dst-safety/per-run-flags/dst-run-flags.feature) (3)
- **DST transition warnings**: [Warning about upcoming DST transitions](dst-safety/transition-warnings/dst-transition-warnings.feature) (3)

## Distribution and Developer Tooling
Installing, packaging, containerising and developing the tool.

- **Container image**: [Running the CLI from the container image](operations/container-image/container-image.feature) (2)
- **One-line installer**: [Installing the CLI with one command](operations/installer/one-line-installer.feature) (2)

## Run Times
Working out when a schedule actually fires, in the user's time zone.

- **Day-of-month and weekday matching**: [Which days a dialect schedule fires on](run-times/day-matching/converted-schedule-day-rules.feature) (4), [Combining day-of-month and weekday](run-times/day-matching/day-matching.feature) (1)
- **Next runs**: [Listing upcoming runs](run-times/next-runs/next-runs.feature) (1)
- **Runs within a time window**: [Listing runs within a time window](run-times/time-window/runs-in-window.feature) (3)

## Schedule Explanation
Turning a schedule into plain language, and plain-language phrases back into schedules.

- **Schedules cron cannot express**: [Explaining intervals cron cannot express](schedule-explanation/beyond-cron/beyond-cron.feature) (4)
- **Phrase to cron**: [Writing a schedule as an English phrase](schedule-explanation/phrase-to-cron/phrase-to-cron.feature) (2)
- **Plain-language descriptions**: [Describing a cron schedule in plain language](schedule-explanation/plain-language/describing-schedules.feature) (3)
