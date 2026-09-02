#!/usr/bin/env python3
"""cron-translate — cron expressions in human terms.

cron-translate '*/15 9-17 * * 1-5'
cron-translate '0 3 * * *' --tz Europe/Rome --next 5
cron-translate '0 2 * * 0' --tz America/New_York   # warns about DST skips
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter

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


def describe(expr):
    """Render a 5-field cron expression as a human-readable sentence."""
    minute, hour, dom, month, dow = expr.split()

    # time-of-day
    if "*" not in (minute, hour) and minute.isdigit() and hour.isdigit():
        time_part = f"at {int(hour):02d}:{int(minute):02d}"
    else:
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
        time_part = ", ".join(bits)

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
    return f"{time_part}, {' and '.join(day_bits)}"


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

    prefix = text[: time_match.start()]
    if "every weekday" in prefix:
        dow = "1-5"
    elif "every weekend" in prefix:
        dow = "6,0"
    else:
        dow = next((str(num) for name, num in DOW_NUMS.items() if name in prefix), "*")
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


def main(argv=None):
    """CLI entry point: describe a cron expression and list its next runs."""
    parser = argparse.ArgumentParser(
        prog="cron-translate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("expression", help="5-field cron expression (quote it)")
    parser.add_argument("--tz", default="UTC", help="IANA timezone for next runs (default UTC)")
    parser.add_argument("--next", type=int, default=3, dest="count", help="how many next runs to show")
    parser.add_argument("--no-dst-check", action="store_true", help="skip DST warnings")
    parser.add_argument(
        "--between",
        nargs=2,
        metavar=("START", "END"),
        help="list every run within [START, END] (ISO 8601, e.g. 2026-07-15T00:00)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    expr = args.expression.strip()
    if not croniter.is_valid(expr):
        translated = phrase_to_cron(expr)
        if translated and croniter.is_valid(translated):
            expr = translated
        else:
            if args.json:
                print(json.dumps({"error": f"invalid cron expression: {expr}"}))
            else:
                print(
                    f"cron-translate: invalid cron expression: {expr!r}",
                    file=sys.stderr,
                )
            return 64

    zone = ZoneInfo(args.tz)
    if args.between:
        start = _parse_dt(args.between[0], zone)
        end = _parse_dt(args.between[1], zone)
        runs = runs_between(expr, start, end)
    else:
        schedule = croniter(expr, datetime.now(zone))
        runs = [schedule.get_next(datetime) for _ in range(args.count)]

    warnings = dst_warnings(expr, args.tz) if not args.no_dst_check and args.tz != "UTC" else []

    if args.json:
        print(
            json.dumps(
                {
                    "expression": expr,
                    "description": describe(expr),
                    "tz": args.tz,
                    "runs": [r.isoformat() for r in runs],
                    "dst_warnings": warnings,
                }
            )
        )
        return 0

    print(f"{expr}\n  → {describe(expr)}\n")
    if args.between:
        print(f"Runs between {start:%Y-%m-%d %H:%M %Z} and {end:%Y-%m-%d %H:%M %Z}: {len(runs)}")
        for run in runs:
            print(f"  {run:%Y-%m-%d %H:%M %Z}")
    else:
        print(f"Next {args.count} runs ({args.tz}):")
        for run in runs:
            delta = run - datetime.now(zone)
            hours = delta / timedelta(hours=1)
            rel = f"in {delta.days}d" if delta.days else f"in {hours:.1f}h"
            print(f"  {run:%Y-%m-%d %H:%M %Z}  ({rel})")

    for warning in warnings:
        print(f"\n⚠ {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
