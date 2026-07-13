#!/usr/bin/env python3
"""cron-translate — cron expressions in human terms.

cron-translate '*/15 9-17 * * 1-5'
cron-translate '0 3 * * *' --tz Europe/Rome --next 5
cron-translate '0 2 * * 0' --tz America/New_York   # warns about DST skips
"""

import argparse
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter

DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
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
        m = _field_phrase(minute, "minute")
        h = _field_phrase(hour, "hour")
        if m:
            bits.append(m if not minute.isdigit() else f"at minute {minute}")
        else:
            bits.append("every minute")
        if h:
            bits.append(
                f"past hour {h}"
                if hour.isdigit()
                else f"during {h}" if not h.startswith("every") else h
            )
        time_part = ", ".join(bits)

    day_bits = []
    d = _field_phrase(
        dow, "weekday", names=DOW[-1:] + DOW[:-1] + DOW[-1:]
    )  # cron: 0 and 7 = Sunday
    if d:
        day_bits.append(f"on {d}")
    dm = _field_phrase(dom, "day of month")
    if dm:
        day_bits.append(f"on day {dm} of the month")
    mo = _field_phrase(month, "month", names=[None] + MONTHS)
    if mo:
        day_bits.append(f"in {mo}")
    if not day_bits:
        day_bits.append("every day")
    return f"{time_part}, {' and '.join(day_bits)}"


def dst_warnings(expr, tz, runs=100):
    """Detect schedule times that get skipped or doubled by DST transitions."""
    warnings = []
    zone = ZoneInfo(tz)
    it = croniter(expr, datetime.now(zone))
    prev = None
    for _ in range(runs):
        nxt = it.get_next(datetime)
        if prev is not None:
            if prev.utcoffset() != nxt.utcoffset():
                warnings.append(
                    f"DST transition between {prev:%Y-%m-%d %H:%M %Z} and {nxt:%Y-%m-%d %H:%M %Z}: "
                    "a run may be skipped (spring forward) or duplicated (fall back)"
                )
        prev = nxt
    return warnings[:3]


def main(argv=None):
    """CLI entry point: describe a cron expression and list its next runs."""
    p = argparse.ArgumentParser(
        prog="cron-translate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("expression", help="5-field cron expression (quote it)")
    p.add_argument(
        "--tz", default="UTC", help="IANA timezone for next runs (default UTC)"
    )
    p.add_argument(
        "--next", type=int, default=3, dest="count", help="how many next runs to show"
    )
    p.add_argument("--no-dst-check", action="store_true", help="skip DST warnings")
    args = p.parse_args(argv)

    expr = args.expression.strip()
    if not croniter.is_valid(expr):
        print(f"cron-translate: invalid cron expression: {expr!r}", file=sys.stderr)
        return 64

    print(f"{expr}\n  → {describe(expr)}\n")
    zone = ZoneInfo(args.tz)
    it = croniter(expr, datetime.now(zone))
    print(f"Next {args.count} runs ({args.tz}):")
    for _ in range(args.count):
        nxt = it.get_next(datetime)
        delta = nxt - datetime.now(zone)
        hours = delta / timedelta(hours=1)
        rel = f"in {delta.days}d" if delta.days else f"in {hours:.1f}h"
        print(f"  {nxt:%Y-%m-%d %H:%M %Z}  ({rel})")

    if not args.no_dst_check and args.tz != "UTC":
        for w in dst_warnings(expr, args.tz):
            print(f"\n⚠ {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
