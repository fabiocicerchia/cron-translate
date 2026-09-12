#!/usr/bin/env python3
"""cron-translate — cron expressions in human terms.

cron-translate '*/15 9-17 * * 1-5'
cron-translate '0 3 * * *' --tz Europe/Rome --next 5
cron-translate '0 2 * * 0' --tz America/New_York   # flags the DST-affected runs
cron-translate convert --from quartz --to eventbridge '0 0 12 ? * MON-FRI *'
"""

import argparse
import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from cron_descriptor import ExpressionDescriptor, Options
from croniter import croniter

import cron_dialects as dialects

LOGGER = logging.getLogger("cron-translate")

# sysexits(3). A usage error is an expression this tool cannot read at all; a
# data error is one it read perfectly well and cannot honestly convert.
EXIT_OK = 0
EXIT_USAGE = 64
EXIT_IMPOSSIBLE = 65

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
# Noon on a 12-hour clock: 12pm stays 12, 12am becomes 0.
NOON_ON_12_HOUR_CLOCK = 12
HOUR_MAX = 23
MINUTE_MAX = 59
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY
MONTHS_PER_YEAR = 12
DST_SCAN_RUNS = 100
MAX_DST_WARNINGS = 3
DEFAULT_RUNS = 3
# Field counts at which croniter's sixth field is seconds (and its seventh,
# if present, the year).
CRONITER_SECONDS_FIELDS = (6, 7)

SKIPPED = "DST: this wall-clock time does not exist (spring forward) — the run is skipped or shifted"
DOUBLED = "DST: this wall-clock time happens twice (fall back) — the run may fire twice"

_INTERVAL_RE = re.compile(r"^every\s+(\d+)\s+(minute|hour|day|week|month)s?$", re.IGNORECASE)
_AT_TIME_RE = re.compile(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)
_NTH_DOW_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|last)\s+"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+of\s+the\s+month\b",
    re.IGNORECASE,
)
_LAST_DAY_RE = re.compile(r"\blast\s+day\s+of\s+the\s+month\b", re.IGNORECASE)
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}


# --- describing ------------------------------------------------------------


def _seconds_first(expr: str) -> str:
    """Move croniter's trailing seconds field to the front.

    croniter reads a sixth field as seconds *after* the weekday, and a seventh
    as the year; cron-descriptor reads the Quartz layout, seconds first. Handed
    one as the other, it silently describes the wrong schedule — `0 12 * * 1 0`
    comes back as "only on Sunday, only in January".
    """
    fields = expr.split()
    if len(fields) not in CRONITER_SECONDS_FIELDS:
        return expr
    minute, hour, dom, month, dow, second, *year = fields
    return " ".join([second, minute, hour, dom, month, dow, *year])


def describe(expr: str, *, dow_index_zero: bool = True, seconds_last: bool = False) -> str:
    """Render a cron expression as a human-readable sentence.

    The wording comes from cron-descriptor, which already knows every corner
    of the grammar — `L`, `W`, `#`, seconds, years — in a dozen languages.
    `dow_index_zero` is False for the dialects that number Sunday 1 (Quartz,
    EventBridge) rather than 0. `seconds_last` is True for expressions written
    in croniter's layout rather than Quartz's.
    """
    options = Options()
    options.use_24hour_time_format = True
    options.day_of_week_start_index_zero = dow_index_zero
    try:
        return ExpressionDescriptor(_seconds_first(expr) if seconds_last else expr, options).get_description()
    except Exception:
        # A description is a nicety; never fail a run over one.
        return expr


def describe_schedule(schedule: dialects.Schedule) -> str:
    """Describe a parsed schedule, whatever dialect it arrived in."""
    form = dialects.describable(schedule)
    if form is None:
        return "(no single cron expression says this: both day fields are restricted and systemd ANDs them)"
    expr, dow_index_zero = form
    return describe(expr, dow_index_zero=dow_index_zero)


# --- English to cron -------------------------------------------------------


@dataclass(frozen=True)
class Translation:
    """What an English phrase becomes, and what cron loses on the way.

    `exact` is False whenever `note` explains a gap between what the phrase
    asks for and what cron can say. `cron` is None when there is no honest
    expression at all — the note then carries the closest thing there is.
    """

    cron: str | None
    note: str | None = None
    exact: bool = True


def _to_24_hour(time_match: re.Match[str]) -> tuple[int, int] | None:
    """Turn an 'at H[:MM] [am|pm]' match into (hour, minute), or None if out of range."""
    hour, minute, ampm = time_match.groups()
    hour, minute = int(hour), int(minute or 0)
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != NOON_ON_12_HOUR_CLOCK:
            hour += NOON_ON_12_HOUR_CLOCK
        elif ampm == "am" and hour == NOON_ON_12_HOUR_CLOCK:
            hour = 0
    if not (0 <= hour <= HOUR_MAX and 0 <= minute <= MINUTE_MAX):
        return None
    return hour, minute


def _weekday_field(prefix: str) -> str:
    """Read the day-of-week cron field out of the words preceding the time."""
    if "every weekday" in prefix:
        return "1-5"
    if "every weekend" in prefix:
        return "6,0"
    return next((str(num) for name, num in DOW_NUMS.items() if name in prefix), "*")


def _beyond_cron(label: str, unit: str) -> Translation:
    """An interval no crontab entry repeats, however the fields are arranged."""
    return Translation(
        None,
        f"cron repeats inside a field, and none of its fields can count {label}: there is no crontab entry "
        f"for it, exact or otherwise. A systemd timer says it directly — `OnUnitActiveSec={unit}` — counting "
        "from the last run; otherwise the job has to keep its own timestamp and exit early.",
        exact=False,
    )


def _minute_interval(every: int) -> Translation:
    if every <= MINUTE_MAX:
        if MINUTES_PER_HOUR % every == 0:
            return Translation(f"*/{every} * * * *")
        return Translation(
            f"*/{every} * * * *",
            f"cron's `*/{every}` restarts at the top of every hour, so the gap across :00 is "
            f"{MINUTES_PER_HOUR % every} minutes rather than {every}. A step that divides 60 "
            "(2, 3, 4, 5, 6, 10, 12, 15, 20, 30) is the only one cron spaces evenly.",
            exact=False,
        )
    lines = _interval_lines(every)
    if not lines:
        return _beyond_cron(f"{every} minutes", f"{every}min")
    return Translation(
        None,
        f"cron's minute field stops at 59, so `every {every} minutes` is not one crontab entry. "
        f"Closest: {'; '.join(lines)}. A systemd timer says it directly — `OnUnitActiveSec={every}min` — and "
        "it counts from the last run rather than from the top of the hour.",
        exact=False,
    )


def _interval_lines(every: int) -> list[str]:
    """Crontab entries that together fire every `every` minutes, if they exist."""
    if MINUTES_PER_DAY % every:
        return []
    by_minute: dict[int, list[int]] = {}
    for offset in range(0, MINUTES_PER_DAY, every):
        by_minute.setdefault(offset % MINUTES_PER_HOUR, []).append(offset // MINUTES_PER_HOUR)
    return [f"{minute} {','.join(str(h) for h in hours)} * * *" for minute, hours in sorted(by_minute.items())]


def _hour_interval(every: int) -> Translation:
    if every == HOURS_PER_DAY:
        return Translation("0 0 * * *")
    if every > HOURS_PER_DAY:
        # 36 hours alternates midnight and noon on alternating days: cron has
        # no field that counts days two at a time against the clock.
        return _beyond_cron(f"{every} hours", f"{every}h")
    if HOURS_PER_DAY % every == 0:
        return Translation(f"0 */{every} * * *")
    return Translation(
        f"0 */{every} * * *",
        f"cron's `*/{every}` restarts at midnight, so the gap across 00:00 is "
        f"{HOURS_PER_DAY % every} hours rather than {every}.",
        exact=False,
    )


def _day_interval(every: int) -> Translation:
    if every == 1:
        return Translation("0 0 * * *")
    if every > dialects.DOM_MAX:
        # `*/40` in a 1-31 field matches nothing past the 1st, so cron would
        # quietly turn "every 40 days" into "the 1st of every month".
        return _beyond_cron(f"{every} days", f"{every}d")
    return Translation(
        f"0 0 */{every} * *",
        f"cron's day-of-month step restarts on the 1st of every month, so `*/{every}` fires on the 1st "
        f"of each month regardless — the gap across a month boundary is not {every} days. A systemd timer "
        f"(`OnUnitActiveSec={every}d`) or a job that keeps its own timestamp is the only exact answer.",
        exact=False,
    )


def _week_interval(every: int, dow: str) -> Translation:
    if every == 1:
        return Translation(f"0 0 * * {dow if dow != '*' else 0}")
    return Translation(
        None,
        f"cron has no week counter: the day-of-week field repeats every week, so `every {every} weeks` "
        f"cannot be written. Closest: run weekly with `0 0 * * {dow if dow != '*' else 0}` and let the job "
        f"decide (`[ $(( $(date +%V) % {every} )) -eq 0 ] || exit 0`), or use a systemd timer with "
        f"`OnUnitActiveSec={every}w`.",
        exact=False,
    )


def _month_interval(every: int) -> Translation:
    if every == 1:
        return Translation("0 0 1 * *")
    if every == MONTHS_PER_YEAR:
        return Translation("0 0 1 1 *")
    if every > MONTHS_PER_YEAR:
        return _beyond_cron(f"{every} months", f"{every}months")
    if MONTHS_PER_YEAR % every == 0:
        return Translation(f"0 0 1 */{every} *")
    return Translation(
        f"0 0 1 */{every} *",
        f"cron's month step restarts in January, so `*/{every}` fires in January every year and the gap "
        f"across the year boundary is {MONTHS_PER_YEAR % every} months rather than {every}.",
        exact=False,
    )


def _interval_translation(every: int, unit: str, dow: str) -> Translation:
    if every < 1:
        return Translation(None, "an interval of zero is not a schedule", exact=False)
    handlers: dict[str, Callable[[], Translation]] = {
        "minute": lambda: _minute_interval(every),
        "hour": lambda: _hour_interval(every),
        "day": lambda: _day_interval(every),
        "week": lambda: _week_interval(every, dow),
        "month": lambda: _month_interval(every),
    }
    return handlers[unit]()


def _nth_weekday_translation(match: re.Match[str]) -> Translation:
    ordinal, weekday = match.group(1).lower(), match.group(2).lower()
    quartz_dow = DOW_NUMS[weekday] + 1
    term = f"{quartz_dow}L" if ordinal == "last" else f"{quartz_dow}#{_ORDINALS[ordinal]}"
    return Translation(
        None,
        f"vixie cron has no `#` or `L`, so it cannot pick the {ordinal} {weekday.title()} of a month. "
        f"Quartz and EventBridge can: `0 0 0 ? * {term} *`. Writing a day-of-month range instead does not "
        "work — vixie ORs day-of-month against day-of-week when both are restricted, so `0 0 15-21 * 5` "
        "fires every Friday *and* every day from the 15th to the 21st. "
        f"Try: cron-translate convert --from quartz --to vixie '0 0 0 ? * {term} *'.",
        exact=False,
    )


def _last_day_translation() -> Translation:
    return Translation(
        None,
        "vixie cron has no `L`, so it cannot say 'the last day of the month': `0 0 28-31 * *` fires up to "
        "four times, and `0 0 31 * *` skips the short months. Quartz and EventBridge say it directly — "
        "`0 0 0 L * ? *` — and systemd writes it `*-*-~01 00:00:00`.",
        exact=False,
    )


def translate_phrase(phrase: str) -> Translation | None:
    """Turn an English phrase into cron, saying where cron cannot follow.

    Returns None when the phrase is not one this tool recognises at all —
    which is different from a phrase it understands and cron cannot express.
    """
    text = phrase.strip().lower()

    nth = _NTH_DOW_RE.search(text)
    if nth:
        return _nth_weekday_translation(nth)
    if _LAST_DAY_RE.search(text):
        return _last_day_translation()

    interval = _INTERVAL_RE.match(text)
    if interval:
        every, unit = interval.groups()
        return _interval_translation(int(every), unit.lower(), "*")

    time_match = _AT_TIME_RE.search(text)
    if not time_match:
        return None
    clock = _to_24_hour(time_match)
    if clock is None:
        return None
    hour, minute = clock
    dow = _weekday_field(text[: time_match.start()])
    return Translation(f"{minute} {hour} * * {dow}")


def phrase_to_cron(phrase: str) -> str | None:
    """The cron expression for an English phrase, or None when there isn't one.

    `translate_phrase` is the richer form: it also says *why* there isn't one.
    """
    translation = translate_phrase(phrase)
    return translation.cron if translation else None


# --- next runs and DST -----------------------------------------------------


def _parse_dt(text: str, zone: ZoneInfo) -> datetime:
    """Parse an ISO 8601 datetime, defaulting to `zone` when it has no offset."""
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=zone)


def _schedule(expr: str, start: datetime) -> croniter:
    """A croniter reading `expr` the way the crontab on the box will read it.

    `implement_cron_bug` is croniter's name for what Vixie and ISC cron
    actually do: day-of-month and day-of-week must both match, rather than
    either of them being enough, whenever
    either field is written with a star. Without it `0 0 */10 * 1-5` is
    reported as "every tenth day or every weekday" when the machine will run
    it on the 1st, 11th, 21st and 31st only, and then only on weekdays. It is
    also the rule `convert` models, so both halves of this tool agree.
    """
    return croniter(expr, start, implement_cron_bug=True)


def runs_between(expr: str, start: datetime, end: datetime) -> list[datetime]:
    """List every run of expr in [start, end], both tz-aware datetimes."""
    schedule = _schedule(expr, start)
    runs: list[datetime] = []
    while True:
        run = schedule.get_next(datetime)
        if run > end:
            break
        runs.append(run)
    return runs


def dst_warnings(expr: str, tz: str, runs: int = DST_SCAN_RUNS) -> list[str]:
    """Detect schedule times that get skipped or doubled by DST transitions."""
    warnings: list[str] = []
    zone = ZoneInfo(tz)
    schedule = _schedule(expr, datetime.now(zone))
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


def _is_gap(wall: datetime, zone: tzinfo) -> bool:
    """True when this wall-clock time does not exist in `zone` (spring forward)."""
    aware = wall.replace(tzinfo=zone)
    return aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != wall


def _is_ambiguous(wall: datetime, zone: tzinfo) -> bool:
    """True when this wall-clock time happens twice in `zone` (fall back)."""
    return wall.replace(tzinfo=zone, fold=0).utcoffset() != wall.replace(tzinfo=zone, fold=1).utcoffset()


def dst_notes(runs: list[datetime], fires_at: Callable[[datetime], bool]) -> list[str | None]:
    """One note per run: skipped, doubled, or None.

    A run in the fall-back hour is reported whether the scheduler emits it
    once or twice. A run in the spring-forward gap shows up either as a
    wall-clock time that does not exist, or — because croniter moves it to the
    next real minute — as a run that no longer matches its own expression.

    The gap is tested first: a time inside it also has two different offsets
    across `fold`, so the ambiguity test cannot tell the two apart on its own.
    """
    notes: list[str | None] = []
    for run in runs:
        zone = run.tzinfo
        wall = run.replace(tzinfo=None)
        if zone is None:
            notes.append(None)
        elif _is_gap(wall, zone) or not fires_at(wall):
            notes.append(SKIPPED)
        elif _is_ambiguous(wall, zone):
            notes.append(DOUBLED)
        else:
            notes.append(None)
    return notes


def _relative(run: datetime, now: datetime) -> str:
    delta = run - now
    hours = delta / timedelta(hours=1)
    return f"in {delta.days}d" if delta.days else f"in {hours:.1f}h"


# --- the describe command --------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """The CLI surface: arguments, defaults and help text."""
    parser = argparse.ArgumentParser(
        prog="cron-translate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run `cron-translate convert --help` for the dialect converter.",
    )
    parser.add_argument("expression", help="5-field cron expression (quote it)")
    parser.add_argument("--tz", default="UTC", help="IANA timezone for next runs (default UTC)")
    parser.add_argument("--next", type=int, default=DEFAULT_RUNS, dest="count", help="how many next runs to show")
    parser.add_argument(
        "--no-dst-check", action="store_true", help="skip the DST checks (per-run flags and transition warnings)"
    )
    parser.add_argument(
        "--between",
        nargs=2,
        metavar=("START", "END"),
        help="list every run within [START, END] (ISO 8601, e.g. 2026-07-15T00:00)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def _collect_runs(
    args: argparse.Namespace, expr: str, zone: ZoneInfo
) -> tuple[list[datetime], tuple[datetime, datetime] | None]:
    """The runs to show, plus the explicit [start, end] window when --between was given."""
    if args.between:
        start = _parse_dt(args.between[0], zone)
        end = _parse_dt(args.between[1], zone)
        return runs_between(expr, start, end), (start, end)
    schedule = _schedule(expr, datetime.now(zone))
    return [schedule.get_next(datetime) for _ in range(args.count)], None


@dataclass(frozen=True)
class Report:
    """Everything the describe command found, before it is written out."""

    expr: str
    runs: list[datetime]
    window: tuple[datetime, datetime] | None
    warnings: list[str]
    notes: list[str | None]
    translation: Translation | None


def _render_text(args: argparse.Namespace, report: Report) -> str:
    """The human-readable report: the sentence, the runs, then any DST warnings.

    Returns the text rather than printing it, so a test can read the report
    without going through capsys and main has one place that writes to stdout.
    """
    lines = [f"{report.expr}\n  → {describe(report.expr, seconds_last=True)}\n"]
    if report.translation and report.translation.note:
        lines.append(f"⚠ {report.translation.note}\n")
    if report.window:
        start, end = report.window
        lines.append(f"Runs between {start:%Y-%m-%d %H:%M %Z} and {end:%Y-%m-%d %H:%M %Z}: {len(report.runs)}")
    else:
        lines.append(f"Next {args.count} runs ({args.tz}):")

    now = datetime.now(ZoneInfo(args.tz))
    for run, note in zip(report.runs, report.notes, strict=True):
        relative = "" if report.window else f"  ({_relative(run, now)})"
        flag = f"  ⚠ {note}" if note else ""
        lines.append(f"  {run:%Y-%m-%d %H:%M %Z}{relative}{flag}")

    lines.extend(f"\n⚠ {warning}" for warning in report.warnings)
    return "\n".join(lines)


def _render_json(args: argparse.Namespace, report: Report) -> str:
    return json.dumps(
        {
            "expression": report.expr,
            "description": describe(report.expr, seconds_last=True),
            "tz": args.tz,
            "runs": [run.isoformat() for run in report.runs],
            "run_dst": report.notes,
            "dst_warnings": report.warnings,
            "note": report.translation.note if report.translation else None,
        }
    )


def _resolve_expression(args: argparse.Namespace) -> tuple[str, Translation | None] | None:
    """The cron expression to work on, and the phrase it came from — or None."""
    expr = args.expression.strip()
    if croniter.is_valid(expr):
        return expr, None
    translation = translate_phrase(expr)
    if translation is None or translation.cron is None or not croniter.is_valid(translation.cron):
        _fail(args, expr, translation)
        return None
    return translation.cron, translation


def _fail(args: argparse.Namespace, expr: str, translation: Translation | None) -> None:
    reason = translation.note if translation and translation.note else f"invalid cron expression: {expr!r}"
    if args.json:
        print(json.dumps({"error": reason}))  # noqa: T201 — the tool's output
    elif translation and translation.note:
        LOGGER.error("%s", reason)
    else:
        LOGGER.error("invalid cron expression: %r", expr)


def _describe_main(argv: list[str]) -> int:
    """Describe one expression and list its next runs."""
    args = _build_parser().parse_args(argv)
    resolved = _resolve_expression(args)
    if resolved is None:
        return EXIT_USAGE
    expr, translation = resolved

    zone = ZoneInfo(args.tz)
    runs, window = _collect_runs(args, expr, zone)
    check_dst = not args.no_dst_check
    # With --between, every run in the window is flagged individually below;
    # a lookahead scan from *now* would report transitions outside it.
    scan = check_dst and args.tz != "UTC" and not args.between
    warnings = dst_warnings(expr, args.tz) if scan else []
    notes: list[str | None] = (
        dst_notes(runs, lambda wall: croniter.match(expr, wall)) if check_dst else [None] * len(runs)
    )
    report = Report(expr, runs, window, warnings, notes, translation)

    print(_render_json(args, report) if args.json else _render_text(args, report))  # noqa: T201 — the tool's output
    return EXIT_OK


# --- the convert command ---------------------------------------------------


def _build_convert_parser() -> argparse.ArgumentParser:
    known = ", ".join(sorted(dialects.DIALECTS))
    parser = argparse.ArgumentParser(
        prog="cron-translate convert",
        description=f"Convert a schedule between cron dialects ({known}).",
    )
    parser.add_argument("expression", help="the schedule in the source dialect (quote it)")
    parser.add_argument("--from", dest="source", required=True, help=f"source dialect: {known}")
    parser.add_argument("--to", dest="target", required=True, help=f"target dialect: {known}")
    parser.add_argument("--tz", default="UTC", help="IANA timezone for the proof runs (default UTC)")
    parser.add_argument("--next", type=int, default=DEFAULT_RUNS, dest="count", help="how many next runs to show")
    parser.add_argument("--no-dst-check", action="store_true", help="skip DST flags on the runs")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def _proof_runs(
    conversion: dialects.Conversion, args: argparse.Namespace
) -> tuple[list[datetime], list[datetime], list[str | None]]:
    """The next runs of both sides on one clock, with DST notes on the source."""
    now = datetime.now(ZoneInfo(args.tz))
    source_runs = dialects.next_runs(conversion.schedule, now, args.count)
    target_runs = dialects.next_runs(conversion.target_schedule, now, args.count)
    notes: list[str | None] = (
        dst_notes(source_runs, lambda wall: dialects.matches(conversion.schedule, wall))
        if not args.no_dst_check
        else [None] * len(source_runs)
    )
    return source_runs, target_runs, notes


def _render_conversion(
    conversion: dialects.Conversion,
    args: argparse.Namespace,
    runs: tuple[list[datetime], list[datetime], list[str | None]],
) -> str:
    source_runs, target_runs, notes = runs
    width = max(len(conversion.source.name), len(conversion.target.name))
    lines = [
        f"{conversion.source.name:<{width}}  {conversion.source_expr}",
        f"{conversion.target.name:<{width}}  {conversion.target_expr}",
        f"\n  → {describe_schedule(conversion.schedule)}\n",
        f"Next {args.count} runs ({args.tz}), both dialects on the same clock:",
    ]
    column = max(len(conversion.source.name), 19)
    lines.append(f"  {conversion.source.name:<{column}}  {conversion.target.name}")
    for index in range(max(len(source_runs), len(target_runs))):
        left = f"{source_runs[index]:%Y-%m-%d %H:%M:%S}" if index < len(source_runs) else "—"
        right = f"{target_runs[index]:%Y-%m-%d %H:%M:%S}" if index < len(target_runs) else "—"
        note = notes[index] if index < len(notes) else None
        flag = f"  ⚠ {note}" if note else ""
        lines.append(f"  {left:<{column}}  {right}{flag}")
    if source_runs != target_runs:
        lines.append("\n⚠ the two expressions do not agree — this is a bug in cron-translate, please report it")
    lines.extend(f"\n⚠ {caveat}" for caveat in conversion.caveats)
    return "\n".join(lines)


def _render_conversion_json(
    conversion: dialects.Conversion,
    args: argparse.Namespace,
    runs: tuple[list[datetime], list[datetime], list[str | None]],
) -> str:
    source_runs, target_runs, notes = runs
    return json.dumps(
        {
            "from": conversion.source.name,
            "to": conversion.target.name,
            "source": conversion.source_expr,
            "target": conversion.target_expr,
            "description": describe_schedule(conversion.schedule),
            "tz": args.tz,
            "source_runs": [run.isoformat() for run in source_runs],
            "target_runs": [run.isoformat() for run in target_runs],
            "run_dst": notes,
            "agree": source_runs == target_runs,
            "caveats": list(conversion.caveats),
        }
    )


def _convert_main(argv: list[str]) -> int:
    """Convert one expression between dialects, or refuse and say why."""
    args = _build_convert_parser().parse_args(argv)
    try:
        conversion = dialects.convert(args.expression, args.source, args.target)
    except dialects.NotExpressibleError as impossible:
        _report_impossible(args, impossible)
        return EXIT_IMPOSSIBLE
    except dialects.DialectError as error:
        _report_dialect_error(args, error)
        return EXIT_USAGE

    runs = _proof_runs(conversion, args)
    renderer = _render_conversion_json if args.json else _render_conversion
    print(renderer(conversion, args, runs))  # noqa: T201 — the tool's output
    return EXIT_OK if runs[0] == runs[1] else EXIT_IMPOSSIBLE


def _report_dialect_error(args: argparse.Namespace, error: dialects.DialectError) -> None:
    if args.json:
        print(json.dumps({"error": str(error)}))  # noqa: T201 — the tool's output
    else:
        LOGGER.error("%s", error)


def _report_impossible(args: argparse.Namespace, impossible: dialects.NotExpressibleError) -> None:
    if args.json:
        print(  # noqa: T201 — the tool's output
            json.dumps({"error": impossible.reason, "closest": impossible.closest, "impossible": True})
        )
        return
    LOGGER.error("cannot convert to %s: %s", args.target, impossible.reason)
    if impossible.closest:
        LOGGER.error("closest %s expression, which is NOT equivalent: %s", args.target, impossible.closest)


# --- entry point -----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: describe an expression, or convert one between dialects."""
    # force=True so a second call in the same process (the tests) rebinds the
    # handler to the current sys.stderr instead of silently reusing the first.
    logging.basicConfig(format="%(name)s: %(message)s", stream=sys.stderr, level=logging.INFO, force=True)
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "convert":
        return _convert_main(arguments[1:])
    return _describe_main(arguments)


if __name__ == "__main__":
    sys.exit(main())
