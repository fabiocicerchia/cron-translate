#!/usr/bin/env python3
"""cron-translate — cron expressions in human terms.

cron-translate '*/15 9-17 * * 1-5'
cron-translate '0 3 * * *' --tz Europe/Rome --next 5
cron-translate '0 2 * * 0' --tz America/New_York   # warns about DST skips
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter

LOGGER = logging.getLogger("cron-translate")

# sysexits(3): the only failure this tool detects itself is a usage error --
# an expression that is neither valid cron nor a phrase it can translate.
EXIT_OK = 0
EXIT_USAGE = 64

DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DOW_NUMS = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 0,
}
# How far ahead dst_warnings walks the schedule, and how many transitions it
# reports: a year of daily runs is enough to cross both DST boundaries, and
# more than a few warnings is noise rather than information.
DST_SCAN_RUNS = 100
MAX_DST_WARNINGS = 3

_INTERVAL_RE = re.compile(r"^every\s+(\d+)\s+(minute|hour)s?$", re.IGNORECASE)
_AT_TIME_RE = re.compile(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _plural(n, unit):
    """Return an 'every N units' phrase, singular when n == 1."""
    return f"every {unit}" if n == 1 else f"every {n} {unit}s"


def _field_phrase(field, unit, names=None):
    """Translate one cron field into a phrase, or None when it's '*'."""
    if field == "*":
        return None
    if field.startswith("*/"):
        return _plural(int(field[2:]), unit)
    parts = []
    for chunk in field.split(","):
        if "/" in chunk:
            rng, step = chunk.split("/")
            parts.append(f"every {step} {unit}s from {rng}")
        elif "-" in chunk:
            lo, hi = chunk.split("-")
            if names:
                lo, hi = names[int(lo) % len(names)], names[int(hi) % len(names)]
            parts.append(f"{lo} through {hi}")
        else:
            parts.append(names[int(chunk) % len(names)] if names else chunk)
    return " and ".join(parts)


def _time_phrase(minute, hour):
    """Render the minute and hour fields as the time-of-day half of the sentence."""
    if "*" not in (minute, hour) and minute.isdigit() and hour.isdigit():
        return f"at {int(hour):02d}:{int(minute):02d}"
    bits = []
    minute_phrase = _field_phrase(minute, "minute")
    hour_phrase = _field_phrase(hour, "hour")
    if minute_phrase:
        bits.append(minute_phrase if not minute.isdigit() else f"at minute {minute}")
    else:
        bits.append("every minute")
    if hour_phrase:
        bits.append(
            f"past hour {hour_phrase}"
            if hour.isdigit()
            else f"during {hour_phrase}"
            if not hour_phrase.startswith("every")
            else hour_phrase
        )
    return ", ".join(bits)


def _day_phrase(dom, month, dow):
    """Render the weekday, day-of-month and month fields as the day half."""
    day_bits = []
    weekday_phrase = _field_phrase(
        dow, "weekday", names=DOW[-1:] + DOW[:-1] + DOW[-1:]
    )  # cron: 0 and 7 = Sunday
    if weekday_phrase:
        day_bits.append(f"on {weekday_phrase}")
    day_of_month_phrase = _field_phrase(dom, "day of month")
    if day_of_month_phrase:
        day_bits.append(f"on day {day_of_month_phrase} of the month")
    month_phrase = _field_phrase(month, "month", names=[None] + MONTHS)
    if month_phrase:
        day_bits.append(f"in {month_phrase}")
    if not day_bits:
        day_bits.append("every day")
    return " and ".join(day_bits)


def describe(expr):
    """Render a 5-field cron expression as a human-readable sentence."""
    minute, hour, dom, month, dow = expr.split()
    time_part = _time_phrase(minute, hour)
    day_part = _day_phrase(dom, month, dow)
    return f"{time_part}, {day_part}"


def _to_24_hour(time_match):
    """Turn an 'at H[:MM] [am|pm]' match into (hour, minute), or None if out of range."""
    hour, minute, ampm = time_match.groups()
    hour, minute = int(hour), int(minute or 0)
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _weekday_field(prefix):
    """Read the day-of-week cron field out of the words preceding the time."""
    if "every weekday" in prefix:
        return "1-5"
    if "every weekend" in prefix:
        return "6,0"
    return next((str(num) for name, num in DOW_NUMS.items() if name in prefix), "*")


def phrase_to_cron(phrase):
    """Parse common English phrasings ('every weekday at 9am', 'every 15 minutes')
    into a 5-field cron expression, or return None if the phrase isn't recognized."""
    text = phrase.strip().lower()

    interval_match = _INTERVAL_RE.match(text)
    if interval_match:
        every, unit = interval_match.groups()
        return f"*/{every} * * * *" if unit == "minute" else f"0 */{every} * * *"

    time_match = _AT_TIME_RE.search(text)
    if not time_match:
        return None
    clock = _to_24_hour(time_match)
    if clock is None:
        return None
    hour, minute = clock
    dow = _weekday_field(text[: time_match.start()])
    return f"{minute} {hour} * * {dow}"


def _parse_dt(text, zone):
    """Parse an ISO 8601 datetime, defaulting to `zone` when it has no offset."""
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=zone)


def runs_between(expr, start, end):
    """List every run of expr in [start, end], both tz-aware datetimes."""
    schedule = croniter(expr, start)
    runs = []
    while True:
        run = schedule.get_next(datetime)
        if run > end:
            break
        runs.append(run)
    return runs


def dst_warnings(expr, tz, runs=DST_SCAN_RUNS):
    """Detect schedule times that get skipped or doubled by DST transitions."""
    warnings = []
    zone = ZoneInfo(tz)
    schedule = croniter(expr, datetime.now(zone))
    previous_run = None
    for _ in range(runs):
        run = schedule.get_next(datetime)
        if previous_run is not None and previous_run.utcoffset() != run.utcoffset():
            warnings.append(
                f"DST transition between {previous_run:%Y-%m-%d %H:%M %Z} and {run:%Y-%m-%d %H:%M %Z}: "
                "a run may be skipped (spring forward) or duplicated (fall back)"
            )
        previous_run = run
    return warnings[:MAX_DST_WARNINGS]


def _build_parser():
    """The CLI surface: arguments, defaults and help text."""
    parser = argparse.ArgumentParser(
        prog="cron-translate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("expression", help="5-field cron expression (quote it)")
    parser.add_argument("--tz", default="UTC", help="IANA timezone for next runs (default UTC)")
    parser.add_argument(
        "--next", type=int, default=3, dest="count", help="how many next runs to show"
    )
    parser.add_argument("--no-dst-check", action="store_true", help="skip DST warnings")
    parser.add_argument(
        "--between",
        nargs=2,
        metavar=("START", "END"),
        help="list every run within [START, END] (ISO 8601, e.g. 2026-07-15T00:00)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def _collect_runs(args, expr, zone):
    """The runs to show, plus the explicit [start, end] window when --between was given."""
    if args.between:
        start = _parse_dt(args.between[0], zone)
        end = _parse_dt(args.between[1], zone)
        return runs_between(expr, start, end), (start, end)
    schedule = croniter(expr, datetime.now(zone))
    return [schedule.get_next(datetime) for _ in range(args.count)], None


def _render_text(args, expr, runs, window, warnings):
    """Print the human-readable report: the sentence, the runs, then any DST warnings."""
    print(f"{expr}\n  → {describe(expr)}\n")
    if window:
        start, end = window
        print(f"Runs between {start:%Y-%m-%d %H:%M %Z} and {end:%Y-%m-%d %H:%M %Z}: {len(runs)}")
        for run in runs:
            print(f"  {run:%Y-%m-%d %H:%M %Z}")
    else:
        print(f"Next {args.count} runs ({args.tz}):")
        for run in runs:
            delta = run - datetime.now(ZoneInfo(args.tz))
            hours = delta / timedelta(hours=1)
            rel = f"in {delta.days}d" if delta.days else f"in {hours:.1f}h"
            print(f"  {run:%Y-%m-%d %H:%M %Z}  ({rel})")

    for warning in warnings:
        print(f"\n⚠ {warning}")


def main(argv=None):
    """CLI entry point: describe a cron expression and list its next runs."""
    # force=True so a second call in the same process (the tests) rebinds the
    # handler to the current sys.stderr instead of silently reusing the first.
    logging.basicConfig(
        format="%(name)s: %(message)s", stream=sys.stderr, level=logging.INFO, force=True
    )
    args = _build_parser().parse_args(argv)

    expr = args.expression.strip()
    if not croniter.is_valid(expr):
        translated = phrase_to_cron(expr)
        if translated and croniter.is_valid(translated):
            expr = translated
        else:
            if args.json:
                print(json.dumps({"error": f"invalid cron expression: {expr}"}))
            else:
                LOGGER.error("invalid cron expression: %r", expr)
            return EXIT_USAGE

    zone = ZoneInfo(args.tz)
    runs, window = _collect_runs(args, expr, zone)
    warnings = dst_warnings(expr, args.tz) if not args.no_dst_check and args.tz != "UTC" else []

    if args.json:
        print(
            json.dumps(
                {
                    "expression": expr,
                    "description": describe(expr),
                    "tz": args.tz,
                    "runs": [run.isoformat() for run in runs],
                    "dst_warnings": warnings,
                }
            )
        )
        return EXIT_OK

    _render_text(args, expr, runs, window, warnings)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
