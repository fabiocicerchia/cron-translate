"""Cron dialects: one schedule model, five syntaxes.

`cron-translate convert` parses an expression in a source dialect into a
`Schedule` — the dialect-neutral model in this module — and renders that
schedule in a target dialect. A conversion that would have to lie raises
`NotExpressibleError` instead of printing a wrong answer, and a conversion that is
exact but loses a nuance carries caveats alongside it.

The dialects and the rules encoded here:

vixie
    The five-field crontab everyone knows. Day-of-week 0-6 with 0 and 7 both
    Sunday; no ``?``, ``L``, ``W`` or ``#``; day-of-month and day-of-week are
    ORed when both are restricted.
k8s
    Kubernetes CronJob `spec.schedule`: vixie as parsed by robfig/cron v3 —
    same five fields, no ``L``/``W``/``?``/``#``, day-of-week 0-6 only, and
    the timezone lives in `spec.timeZone` rather than in the expression.
eventbridge
    Amazon EventBridge `cron(...)`: six fields with a year and no seconds,
    day-of-week 1-7 with 1 = Sunday, exactly one of day-of-month and
    day-of-week must be ``?``, ``/`` is not accepted in day-of-week, and a
    ``#`` term must be the only term in its field.
quartz
    Six or seven fields with leading seconds and a trailing optional year,
    day-of-week 1-7 with 1 = Sunday, exactly one of day-of-month and
    day-of-week must be ``?``, and the full ``L``/``L-n``/``LW``/``nW``/
    ``nL``/``n#m`` vocabulary.
systemd
    `OnCalendar=` — ``DOW Y-M-D H:M:S [TZ]``. Seconds and years are native,
    ``~n`` counts back from the end of the month, and the weekday is ANDed
    with the date rather than ORed.
"""

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import product

# --- the model -------------------------------------------------------------


@dataclass(frozen=True)
class Every:
    """``*`` (step 1) or ``*/step`` — the whole field, optionally thinned."""

    step: int = 1


@dataclass(frozen=True)
class Span:
    """``5``, ``5-9``, ``5-9/2`` or ``5/2``; `hi` is None for a single value."""

    lo: int
    hi: int | None = None
    step: int = 1


@dataclass(frozen=True)
class LastDom:
    """Day-of-month ``L`` (offset 0) or ``L-3`` (offset 3): days from the end."""

    offset: int = 0


@dataclass(frozen=True)
class NearestWeekday:
    """Day-of-month ``15W``; `day` is None for ``LW``, the last weekday."""

    day: int | None


@dataclass(frozen=True)
class NthDow:
    """Day-of-week ``6#3``: the `nth` `weekday` of the month."""

    weekday: int
    nth: int


@dataclass(frozen=True)
class LastDow:
    """Day-of-week ``6L``: the last `weekday` of the month."""

    weekday: int


Term = Every | Span | LastDom | NearestWeekday | NthDow | LastDow
# A field is a tuple of terms, or None for `?` — "no specific value", which is
# not the same as `*`: it is how Quartz and EventBridge say "the other day
# field decides".
Field = tuple[Term, ...] | None


@dataclass(frozen=True)
class Schedule:
    """A dialect-neutral schedule. Day-of-week is normalised to 0 = Sunday."""

    second: tuple[Term, ...]
    minute: tuple[Term, ...]
    hour: tuple[Term, ...]
    dom: Field
    month: tuple[Term, ...]
    dow: Field
    year: tuple[Term, ...]
    # How day-of-month and day-of-week combine when both are restricted: cron
    # ORs them, systemd ANDs them. The difference is not cosmetic -- see
    # `_day_matches`.
    day_match: str = "or"
    tz: str | None = None


class DialectError(Exception):
    """The expression is not valid in the dialect it was read as."""


class NotExpressibleError(Exception):
    """The target dialect cannot express this schedule.

    `closest` is a target expression that is *not* equivalent but is the
    nearest thing the target can say, offered so the caller has somewhere to
    go. It is never presented as the conversion.
    """

    def __init__(self, reason: str, closest: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.closest = closest


# --- field specifications --------------------------------------------------

NUMERIC = "num"
DAY_OF_MONTH = "dom"
DAY_OF_WEEK = "dow"

MONTH_NAMES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
# Indexed by the normalised value, so DOW_NAMES[0] is Sunday.
DOW_NAMES = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
SYSTEMD_DOW_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")

DAYS_IN_WEEK = 7
DOM_MAX = 31
SATURDAY = 6
SUNDAY = 0
# croniter and Quartz agree on the outer bounds of a year field; EventBridge
# runs further out. Each dialect narrows this in its own spec.
YEAR_MIN = 1970
YEAR_MAX = 2199
# Five years of days is far enough to find the next few runs of anything that
# fires at all -- 29 February in a leap year is the sparsest realistic case.
HORIZON_DAYS = 366 * 5


@dataclass(frozen=True)
class FieldSpec:
    """What one field of one dialect accepts, and how to read its values."""

    name: str
    kind: str
    low: int
    high: int
    names: tuple[str, ...] = ()
    # The value that `names[0]` stands for: 0 for vixie's SUN, 1 for Quartz's.
    name_base: int = 0
    # Which of "?", "L", "L-", "W", "LW", "#", "/" this field accepts.
    allow: frozenset[str] = frozenset()


def _numeric(name: str, low: int, high: int, *, step: bool = True) -> FieldSpec:
    """A plain range field — seconds, minutes, hours, years."""
    return FieldSpec(name=name, kind=NUMERIC, low=low, high=high, allow=frozenset({"/"} if step else set()))


SECOND_SPEC = _numeric("second", 0, 59)
MINUTE_SPEC = _numeric("minute", 0, 59)
HOUR_SPEC = _numeric("hour", 0, 23)
MONTH_SPEC = FieldSpec(name="month", kind=NUMERIC, low=1, high=12, names=MONTH_NAMES, name_base=1, allow=frozenset("/"))


def _dow_spec(base: int, allow: set[str]) -> FieldSpec:
    """A day-of-week field; `base` is the number the dialect gives Sunday."""
    return FieldSpec(
        name="day-of-week",
        kind=DAY_OF_WEEK,
        low=base,
        high=base + DAYS_IN_WEEK - 1,
        names=DOW_NAMES,
        name_base=base,
        allow=frozenset(allow),
    )


def _dom_spec(allow: set[str]) -> FieldSpec:
    return FieldSpec(name="day-of-month", kind=DAY_OF_MONTH, low=1, high=DOM_MAX, allow=frozenset(allow))


# --- parsing ---------------------------------------------------------------

_STEP_RE = re.compile(r"^\d+$")


def _value(text: str, spec: FieldSpec) -> int:
    """Read one field value — a number or a three-letter name — as an int."""
    token = text.strip().upper()
    if not token:
        raise DialectError(f"empty value in the {spec.name} field")
    if token in spec.names:
        return spec.names.index(token) + spec.name_base
    if not token.isdigit():
        raise DialectError(f"{text!r} is not a value the {spec.name} field accepts")
    number = int(token)
    if not spec.low <= number <= spec.high:
        raise DialectError(f"{number} is outside the {spec.name} range {spec.low}-{spec.high}")
    return number


def _normalise_dow(value: int, spec: FieldSpec) -> int:
    """Map a dialect's day-of-week number onto the model's 0 = Sunday."""
    return (value - spec.name_base) % DAYS_IN_WEEK


def _parse_step(text: str, spec: FieldSpec, chunk: str) -> int:
    if not text:
        return 1
    if "/" not in spec.allow:
        raise DialectError(f"the {spec.name} field of this dialect does not accept a step ({chunk!r})")
    if not _STEP_RE.match(text) or int(text) < 1:
        raise DialectError(f"{text!r} is not a step in {chunk!r}")
    return int(text)


def _parse_dom_special(word: str, spec: FieldSpec) -> Term | None:
    """``L``, ``L-3``, ``LW`` and ``15W``, or None when `word` is ordinary."""
    if word == "L":
        _require("L", spec, word)
        return LastDom()
    if word == "LW":
        _require("LW", spec, word)
        return NearestWeekday(None)
    if word.startswith("L-"):
        _require("L-", spec, word)
        offset = word[2:]
        if not offset.isdigit():
            raise DialectError(f"{word!r} is not a day-of-month value")
        return LastDom(int(offset))
    if word.endswith("W") and word[:-1].isdigit():
        _require("W", spec, word)
        return NearestWeekday(_value(word[:-1], spec))
    return None


def _parse_dow_special(word: str, spec: FieldSpec) -> Term | None:
    """``6L``/``FRIL`` and ``6#3``/``FRI#3``, or None when `word` is ordinary."""
    if "#" in word:
        _require("#", spec, word)
        day, _, nth = word.partition("#")
        if not nth.isdigit() or not 1 <= int(nth) <= 5:  # noqa: PLR2004 — a month holds at most five of any weekday
            raise DialectError(f"{word!r}: the count after '#' must be 1-5")
        return NthDow(_normalise_dow(_value(day, spec), spec), int(nth))
    if word.endswith("L") and word != "L":
        _require("L", spec, word)
        return LastDow(_normalise_dow(_value(word[:-1], spec), spec))
    return None


def _require(feature: str, spec: FieldSpec, token: str) -> None:
    if feature not in spec.allow:
        raise DialectError(f"the {spec.name} field of this dialect does not accept {token!r}")


def _parse_term(chunk: str, spec: FieldSpec) -> Term:
    token = chunk.strip().upper()
    special = _parse_dom_special(token, spec) if spec.kind == DAY_OF_MONTH else None
    if spec.kind == DAY_OF_WEEK:
        special = _parse_dow_special(token, spec)
    if special is not None:
        return special

    body, _, step_text = token.partition("/")
    step = _parse_step(step_text, spec, chunk)
    if body == "*":
        return Every(step)
    lo_text, dash, hi_text = body.partition("-")
    lo = _value(lo_text, spec)
    hi = _value(hi_text, spec) if dash else None
    if spec.kind == DAY_OF_WEEK:
        lo = _normalise_dow(lo, spec)
        hi = None if hi is None else _normalise_dow(hi, spec)
    return Span(lo, hi, step)


def parse_field(text: str, spec: FieldSpec) -> Field:
    """Parse one comma-separated cron field into terms, or None for ``?``."""
    body = text.strip()
    if body == "?":
        _require("?", spec, body)
        return None
    if not body:
        raise DialectError(f"the {spec.name} field is empty")
    return tuple(_parse_term(chunk, spec) for chunk in body.split(","))


# --- matching and next runs ------------------------------------------------


def expand(terms: tuple[Term, ...], low: int, high: int) -> tuple[int, ...]:
    """Every value a plain numeric field matches, sorted and deduplicated."""
    values: set[int] = set()
    for term in terms:
        if isinstance(term, Every):
            values.update(range(low, high + 1, term.step))
        elif isinstance(term, Span):
            stop = term.hi if term.hi is not None else (term.lo if term.step == 1 else high)
            values.update(range(term.lo, stop + 1, term.step))
        else:
            raise DialectError(f"{term!r} has no meaning outside a day field")
    return tuple(sorted(values))


def _in_span(value: int, term: Span, high: int) -> bool:
    stop = term.hi if term.hi is not None else (term.lo if term.step == 1 else high)
    return value in range(term.lo, stop + 1, term.step)


def _last_day(day: date) -> int:
    return calendar.monthrange(day.year, day.month)[1]


def _nearest_weekday(day: date, target: int) -> bool:
    """Quartz's ``W``: the weekday nearest `target`, never leaving the month."""
    target = min(target, _last_day(day))
    wanted = date(day.year, day.month, target)
    shift = {SUNDAY: 1, SATURDAY: -1}.get(_weekday(wanted), 0)
    landed = wanted + timedelta(days=shift)
    if landed.month != wanted.month:
        landed = wanted + timedelta(days=-shift * 2)
    return landed == day


def _weekday(day: date) -> int:
    """The model's day-of-week for a date: 0 = Sunday."""
    return (day.weekday() + 1) % DAYS_IN_WEEK


def _last_weekday_of_month(day: date) -> bool:
    last = date(day.year, day.month, _last_day(day))
    shift = {SUNDAY: -2, SATURDAY: -1}.get(_weekday(last), 0)
    return last + timedelta(days=shift) == day


def _dom_matches(terms: tuple[Term, ...], day: date) -> bool:
    last = _last_day(day)
    for term in terms:
        if isinstance(term, Every) and (day.day - 1) % term.step == 0:
            return True
        if isinstance(term, Span) and _in_span(day.day, term, DOM_MAX):
            return True
        if isinstance(term, LastDom) and day.day == last - term.offset:
            return True
        if isinstance(term, NearestWeekday):
            if term.day is None and _last_weekday_of_month(day):
                return True
            if term.day is not None and _nearest_weekday(day, term.day):
                return True
    return False


def _dow_matches(terms: tuple[Term, ...], day: date) -> bool:
    weekday = _weekday(day)
    for term in terms:
        if isinstance(term, Every) and weekday % term.step == 0:
            return True
        if isinstance(term, Span) and _dow_span_matches(weekday, term):
            return True
        if isinstance(term, NthDow) and term.weekday == weekday and (day.day - 1) // DAYS_IN_WEEK + 1 == term.nth:
            return True
        if isinstance(term, LastDow) and term.weekday == weekday and day.day + DAYS_IN_WEEK > _last_day(day):
            return True
    return False


def _dow_span_matches(weekday: int, term: Span) -> bool:
    if term.hi is None:
        return _in_span(weekday, term, DAYS_IN_WEEK - 1)
    if term.lo <= term.hi:
        return _in_span(weekday, term, DAYS_IN_WEEK - 1)
    # FRI-MON wraps through Sunday; cron reads it as two spans, not as empty.
    return weekday >= term.lo or weekday <= term.hi


def is_open(field: Field) -> bool:
    """True when the field places no restriction — ``?`` or a bare ``*``."""
    return field is None or any(isinstance(term, Every) and term.step == 1 for term in field)


def _day_matches(schedule: Schedule, day: date) -> bool:
    dom_open, dow_open = is_open(schedule.dom), is_open(schedule.dow)
    if dom_open and dow_open:
        return True
    if dom_open:
        return _dow_matches(schedule.dow or (), day)
    if dow_open:
        return _dom_matches(schedule.dom or (), day)
    both = (_dom_matches(schedule.dom or (), day), _dow_matches(schedule.dow or (), day))
    return any(both) if schedule.day_match == "or" else all(both)


def matches(schedule: Schedule, moment: datetime) -> bool:
    """True when `schedule` fires at exactly `moment` (to the second)."""
    day = moment.date()
    return (
        day.year in expand(schedule.year, YEAR_MIN, YEAR_MAX)
        and day.month in expand(schedule.month, 1, 12)
        and _day_matches(schedule, day)
        and moment.hour in expand(schedule.hour, 0, 23)
        and moment.minute in expand(schedule.minute, 0, 59)
        and moment.second in expand(schedule.second, 0, 59)
    )


def next_runs(schedule: Schedule, start: datetime, count: int) -> list[datetime]:
    """The next `count` fire times strictly after `start`, in `start`'s zone.

    Walks days rather than seconds, so a schedule that fires once a year costs
    the same as one that fires every minute.
    """
    zone = start.tzinfo
    clock = tuple(product(expand(schedule.hour, 0, 23), expand(schedule.minute, 0, 59), expand(schedule.second, 0, 59)))
    months = frozenset(expand(schedule.month, 1, 12))
    years = frozenset(expand(schedule.year, YEAR_MIN, YEAR_MAX))
    last_year = max(years) if years else YEAR_MAX

    runs: list[datetime] = []
    day = start.date()
    for _ in range(HORIZON_DAYS):
        if day.year > last_year:
            break
        if day.year in years and day.month in months and _day_matches(schedule, day):
            runs.extend(_day_runs(day, clock, start, zone, count - len(runs)))
        if len(runs) >= count:
            break
        day += timedelta(days=1)
    return runs


def _day_runs(
    day: date,
    clock: tuple[tuple[int, int, int], ...],
    start: datetime,
    zone: object,
    wanted: int,
) -> list[datetime]:
    """The fire times on one day that fall after `start`, at most `wanted`."""
    found: list[datetime] = []
    for hour, minute, second in clock:
        moment = datetime.combine(day, time(hour, minute, second), tzinfo=zone)  # pyright: ignore[reportArgumentType]
        if moment > start:
            found.append(moment)
            if len(found) >= wanted:
                break
    return found


# --- rendering -------------------------------------------------------------


def _denormalise_dow(value: int, spec: FieldSpec) -> int:
    return value + spec.name_base


def _render_span(term: Span, spec: FieldSpec) -> str:
    shift = spec.name_base if spec.kind == DAY_OF_WEEK else 0
    lo = term.lo + shift
    if term.hi is None:
        return f"{lo}/{term.step}" if term.step > 1 else str(lo)
    hi = term.hi + shift
    text = f"{lo}-{hi}"
    return f"{text}/{term.step}" if term.step > 1 else text


def _expand_wrapping_dow(term: Span, spec: FieldSpec) -> str:
    """FRI-MON as a comma list: not every dialect reads a wrapping range."""
    days = list(range(term.lo, DAYS_IN_WEEK)) + list(range((term.hi or 0) + 1))
    return ",".join(str(_denormalise_dow(d, spec)) for d in days)


def _render_term(term: Term, spec: FieldSpec) -> str:
    if isinstance(term, Every):
        return "*" if term.step == 1 else f"*/{term.step}"
    if isinstance(term, Span):
        wraps = spec.kind == DAY_OF_WEEK and term.hi is not None and term.lo > term.hi
        return _expand_wrapping_dow(term, spec) if wraps else _render_span(term, spec)
    if isinstance(term, LastDom):
        return "L" if term.offset == 0 else f"L-{term.offset}"
    if isinstance(term, NearestWeekday):
        return "LW" if term.day is None else f"{term.day}W"
    if isinstance(term, NthDow):
        return f"{_denormalise_dow(term.weekday, spec)}#{term.nth}"
    return f"{_denormalise_dow(term.weekday, spec)}L"


def render_field(field: Field, spec: FieldSpec) -> str:
    """Render a field back to text; None becomes ``?``."""
    if field is None:
        return "?"
    return ",".join(_render_term(term, spec) for term in field)


# --- dialect specifications ------------------------------------------------

YEAR_SPEC = _numeric("year", YEAR_MIN, YEAR_MAX)

VIXIE_DOM_SPEC = _dom_spec({"/"})
# Vixie accepts 7 as a second spelling of Sunday; `_normalise_dow` folds it
# back onto 0, which is what every other dialect and this model use.
VIXIE_DOW_SPEC = FieldSpec(
    name="day-of-week", kind=DAY_OF_WEEK, low=0, high=7, names=DOW_NAMES, name_base=0, allow=frozenset("/")
)
# robfig/cron v3, the parser behind Kubernetes CronJob, stops at 6.
K8S_DOW_SPEC = _dow_spec(0, {"/"})

EVENTBRIDGE_DOM_SPEC = _dom_spec({"/", "L", "W", "?"})
# AWS lists the day-of-week wildcards as , - * ? L # -- no '/'.
EVENTBRIDGE_DOW_SPEC = _dow_spec(1, {"L", "#", "?"})
EVENTBRIDGE_YEAR_SPEC = _numeric("year", 1970, 2199)

QUARTZ_DOM_SPEC = _dom_spec({"/", "L", "L-", "W", "LW", "?"})
QUARTZ_DOW_SPEC = _dow_spec(1, {"/", "L", "#", "?"})
QUARTZ_YEAR_SPEC = _numeric("year", 1970, 2099)

SYSTEMD_DOM_SPEC = _dom_spec({"/", "L"})
SYSTEMD_DOW_SPEC = _dow_spec(0, {"/"})

VIXIE_FIELDS = 5
EVENTBRIDGE_FIELDS = 6
QUARTZ_FIELDS = (6, 7)

MACROS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

MIDNIGHT = (Span(0),)
ANY = (Every(),)


def _split(expr: str, expected: tuple[int, ...], dialect: str) -> list[str]:
    fields = expr.split()
    if len(fields) not in expected:
        wanted = " or ".join(str(count) for count in expected)
        raise DialectError(f"{dialect} expects {wanted} fields, got {len(fields)}: {expr!r}")
    return fields


def _terms(field: Field) -> tuple[Term, ...]:
    """Narrow a parsed field that cannot be `?` — the spec forbade it."""
    if field is None:  # pragma: no cover — only reachable if a spec allows '?' here
        raise DialectError("'?' is not a value this field accepts")
    return field


def _expand_macro(expr: str) -> str:
    shorthand = expr.strip().lower()
    if shorthand == "@reboot":
        raise DialectError("@reboot is not a calendar schedule: it has no next run and no equivalent in any dialect")
    return MACROS.get(shorthand, expr.strip())


# --- parsers ---------------------------------------------------------------


def _parse_five_field(expr: str, dow_spec: FieldSpec, dialect: str) -> Schedule:
    minute, hour, dom, month, dow = _split(_expand_macro(expr), (VIXIE_FIELDS,), dialect)
    return Schedule(
        second=MIDNIGHT,
        minute=_terms(parse_field(minute, MINUTE_SPEC)),
        hour=_terms(parse_field(hour, HOUR_SPEC)),
        dom=parse_field(dom, VIXIE_DOM_SPEC),
        month=_terms(parse_field(month, MONTH_SPEC)),
        dow=parse_field(dow, dow_spec),
        year=ANY,
    )


def parse_vixie(expr: str) -> Schedule:
    """Read a five-field crontab entry."""
    return _parse_five_field(expr, VIXIE_DOW_SPEC, "vixie cron")


def parse_k8s(expr: str) -> Schedule:
    """Read a Kubernetes CronJob `spec.schedule`."""
    return _parse_five_field(expr, K8S_DOW_SPEC, "Kubernetes CronJob")


def _check_question_mark(dom: Field, dow: Field, dialect: str) -> None:
    if dom is None and dow is None:
        raise DialectError(f"{dialect} needs a value in one of day-of-month and day-of-week; both are '?'")
    if dom is not None and dow is not None:
        raise DialectError(
            f"{dialect} requires '?' in exactly one of day-of-month and day-of-week; this expression gives both a value"
        )


def parse_eventbridge(expr: str) -> Schedule:
    """Read an EventBridge `cron(...)` body: six fields, ending in a year."""
    body = expr.strip()
    if body.lower().startswith("cron(") and body.endswith(")"):
        body = body[len("cron(") : -1]
    minute, hour, dom, month, dow, year = _split(body, (EVENTBRIDGE_FIELDS,), "EventBridge cron")
    dom_field = parse_field(dom, EVENTBRIDGE_DOM_SPEC)
    dow_field = parse_field(dow, EVENTBRIDGE_DOW_SPEC)
    _check_question_mark(dom_field, dow_field, "EventBridge")
    return Schedule(
        second=MIDNIGHT,
        minute=_terms(parse_field(minute, MINUTE_SPEC)),
        hour=_terms(parse_field(hour, HOUR_SPEC)),
        dom=dom_field,
        month=_terms(parse_field(month, MONTH_SPEC)),
        dow=dow_field,
        year=_terms(parse_field(year, EVENTBRIDGE_YEAR_SPEC)),
    )


def parse_quartz(expr: str) -> Schedule:
    """Read a Quartz expression: seconds first, year optional."""
    fields = _split(expr.strip(), QUARTZ_FIELDS, "Quartz")
    second, minute, hour, dom, month, dow = fields[:6]
    year = fields[6] if len(fields) > 6 else "*"  # noqa: PLR2004 — the seventh field is the year
    dom_field = parse_field(dom, QUARTZ_DOM_SPEC)
    dow_field = parse_field(dow, QUARTZ_DOW_SPEC)
    _check_question_mark(dom_field, dow_field, "Quartz")
    return Schedule(
        second=_terms(parse_field(second, SECOND_SPEC)),
        minute=_terms(parse_field(minute, MINUTE_SPEC)),
        hour=_terms(parse_field(hour, HOUR_SPEC)),
        dom=dom_field,
        month=_terms(parse_field(month, MONTH_SPEC)),
        dow=dow_field,
        year=_terms(parse_field(year, QUARTZ_YEAR_SPEC)),
    )


# --- systemd OnCalendar ----------------------------------------------------

SYSTEMD_SHORTHANDS = {
    "minutely": "*-*-* *:*:00",
    "hourly": "*-*-* *:00:00",
    "daily": "*-*-* 00:00:00",
    "midnight": "*-*-* 00:00:00",
    "weekly": "Mon *-*-* 00:00:00",
    "monthly": "*-*-01 00:00:00",
    "quarterly": "*-01,04,07,10-01 00:00:00",
    "semiannually": "*-01,07-01 00:00:00",
    "yearly": "*-01-01 00:00:00",
    "annually": "*-01-01 00:00:00",
}
SYSTEMD_FULL_DOW = {
    "MONDAY": "MON",
    "TUESDAY": "TUE",
    "WEDNESDAY": "WED",
    "THURSDAY": "THU",
    "FRIDAY": "FRI",
    "SATURDAY": "SAT",
    "SUNDAY": "SUN",
}
DATE_PARTS = 3
SHORT_DATE_PARTS = 2
TIME_PARTS = 3
SHORT_TIME_PARTS = 2
# What is left after the weekday and timezone have been taken off: a date and
# a time, either of which may be omitted.
MAX_CALENDAR_TOKENS = 2


def _systemd_value(text: str, spec: FieldSpec) -> int:
    return _value(SYSTEMD_FULL_DOW.get(text.strip().upper(), text), spec)


def _parse_systemd_term(chunk: str, spec: FieldSpec) -> Term:
    body, _, step_text = chunk.strip().partition("/")
    step = _parse_step(step_text, spec, chunk)
    if body == "*":
        return Every(step)
    if body.startswith("~"):
        _require("L", spec, chunk)
        if not body[1:].isdigit() or int(body[1:]) < 1:
            raise DialectError(f"{chunk!r}: '~' counts back from the end of the month and needs a day number")
        return LastDom(int(body[1:]) - 1)
    lo_text, sep, hi_text = body.partition("..")
    lo = _systemd_value(lo_text, spec)
    hi = _systemd_value(hi_text, spec) if sep else None
    if spec.kind == DAY_OF_WEEK:
        lo = _normalise_dow(lo, spec)
        hi = None if hi is None else _normalise_dow(hi, spec)
    return Span(lo, hi, step)


def _parse_systemd_field(text: str, spec: FieldSpec) -> tuple[Term, ...]:
    return tuple(_parse_systemd_term(chunk, spec) for chunk in text.split(","))


def _looks_like_zone(token: str) -> bool:
    return ("/" in token and not token[0].isdigit()) or token.upper() in {"UTC", "LOCAL"}


def _looks_like_dow(token: str) -> bool:
    head = token.split("..", maxsplit=1)[0].split(",", maxsplit=1)[0].strip().upper()
    return head in DOW_NAMES or head in SYSTEMD_FULL_DOW


def _systemd_date(text: str) -> tuple[tuple[Term, ...], tuple[Term, ...], tuple[Term, ...]]:
    """Split ``Y-M-D`` (or ``M-D``) into year, month and day-of-month terms."""
    parts = text.split("-")
    if len(parts) == SHORT_DATE_PARTS:
        parts = ["*", *parts]
    if len(parts) != DATE_PARTS:
        raise DialectError(f"{text!r} is not a systemd date: expected Y-M-D or M-D")
    year, month, day = parts
    return (
        _parse_systemd_field(year, YEAR_SPEC),
        _parse_systemd_field(month, MONTH_SPEC),
        _parse_systemd_field(day, SYSTEMD_DOM_SPEC),
    )


def _systemd_time(text: str) -> tuple[tuple[Term, ...], tuple[Term, ...], tuple[Term, ...]]:
    parts = text.split(":")
    if len(parts) == SHORT_TIME_PARTS:
        parts = [*parts, "0"]
    if len(parts) != TIME_PARTS:
        raise DialectError(f"{text!r} is not a systemd time: expected H:M or H:M:S")
    hour, minute, second = parts
    return (
        _parse_systemd_field(hour, HOUR_SPEC),
        _parse_systemd_field(minute, MINUTE_SPEC),
        _parse_systemd_field(second, SECOND_SPEC),
    )


def _systemd_tokens(expr: str) -> tuple[str | None, str, str, str | None]:
    """Pull an OnCalendar line apart into weekday, date, time and timezone."""
    text = expr.strip()
    tokens = SYSTEMD_SHORTHANDS.get(text.lower(), text).split()
    if not tokens:
        raise DialectError("empty OnCalendar expression")
    tz = tokens.pop() if len(tokens) > 1 and _looks_like_zone(tokens[-1]) else None
    dow = tokens.pop(0) if _looks_like_dow(tokens[0]) else None
    if len(tokens) > MAX_CALENDAR_TOKENS:
        raise DialectError(f"{expr!r} has more parts than 'DOW Y-M-D H:M:S TZ'")
    date_text = next((token for token in tokens if ":" not in token), "*-*-*")
    time_text = next((token for token in tokens if ":" in token), "00:00:00")
    return dow, date_text, time_text, tz


def parse_systemd(expr: str) -> Schedule:
    """Read a systemd ``OnCalendar=`` value (the documented subset below).

    Supported: the ``daily``/``weekly``/… shorthands, ``DOW Y-M-D H:M:S`` with
    ``*``, ``,``, ``..`` ranges, ``/`` repetition, ``~n`` counting back from
    the end of the month, and a trailing timezone.
    """
    dow_text, date_text, time_text, tz = _systemd_tokens(expr)
    year, month, dom = _systemd_date(date_text)
    hour, minute, second = _systemd_time(time_text)
    return Schedule(
        second=second,
        minute=minute,
        hour=hour,
        dom=dom,
        month=month,
        dow=_parse_systemd_field(dow_text, SYSTEMD_DOW_SPEC) if dow_text else ANY,
        year=year,
        # OnCalendar= requires the weekday *and* the date to match; cron ORs
        # them. Converting either way has to reckon with that.
        day_match="and",
        tz=tz,
    )


# --- formatters ------------------------------------------------------------

QUESTION_MARK_CAVEAT = (
    "`?` (no specific value) has no meaning in a 5-field crontab and is written `*`; "
    "the effect is the same here because the other day field carries the restriction."
)
STAR_TO_QUESTION_CAVEAT = (
    "`*` in both day fields is not legal in this dialect: day-of-week is written `?`, which means the same thing."
)
OR_VS_AND_CAVEAT = (
    "cron ORs day-of-month against day-of-week when both are restricted; "
    "systemd ANDs them. Only one of the two day fields is restricted here, so the readings agree."
)


def _specials(field: Field) -> list[Term]:
    """The terms that are not a plain ``*``, value or range: L, W, # and nL."""
    return [term for term in (field or ()) if not isinstance(term, (Every, Span))]


def _seconds_are_midnight(schedule: Schedule) -> bool:
    return expand(schedule.second, 0, 59) == (0,)


def _reject_specials(schedule: Schedule, dialect: str) -> None:
    found = _specials(schedule.dom) + _specials(schedule.dow)
    if found:
        written = ", ".join(sorted({_render_term(term, QUARTZ_DOW_SPEC) for term in found}))
        raise NotExpressibleError(f"{dialect} has no `L`, `W` or `#`: it cannot express {written}")


def _reject_year(schedule: Schedule, dialect: str) -> None:
    if not is_open(schedule.year):
        raise NotExpressibleError(
            f"{dialect} has no year field, so it cannot limit a schedule to {render_field(schedule.year, YEAR_SPEC)}"
        )


def _reject_and_semantics(schedule: Schedule, dialect: str) -> None:
    if schedule.day_match == "and" and not is_open(schedule.dom) and not is_open(schedule.dow):
        raise NotExpressibleError(
            f"systemd ANDs the weekday against the date, and {dialect} ORs them when both day fields are "
            "restricted. No single expression carries the systemd meaning."
        )


def _five_field_text(schedule: Schedule, dow_spec: FieldSpec, dialect: str) -> str:
    _reject_specials(schedule, dialect)
    _reject_year(schedule, dialect)
    _reject_and_semantics(schedule, dialect)
    dom = "*" if schedule.dom is None else render_field(schedule.dom, VIXIE_DOM_SPEC)
    dow = "*" if schedule.dow is None else render_field(schedule.dow, dow_spec)
    minute = render_field(schedule.minute, MINUTE_SPEC)
    hour = render_field(schedule.hour, HOUR_SPEC)
    month = render_field(schedule.month, MONTH_SPEC)
    return f"{minute} {hour} {dom} {month} {dow}"


def _seconds_caveat(schedule: Schedule, dialect: str, text: str) -> None:
    if not _seconds_are_midnight(schedule):
        raise NotExpressibleError(
            f"{dialect} has no seconds field, and this schedule fires at second "
            f"{render_field(schedule.second, SECOND_SPEC)} rather than only at :00",
            closest=text,
        )


def _day_caveats(schedule: Schedule) -> list[str]:
    caveats: list[str] = []
    if schedule.dom is None or schedule.dow is None:
        caveats.append(QUESTION_MARK_CAVEAT)
    if schedule.day_match == "and" and (is_open(schedule.dom) or is_open(schedule.dow)):
        caveats.append(OR_VS_AND_CAVEAT)
    return caveats


def render_vixie(schedule: Schedule) -> tuple[str, tuple[str, ...]]:
    """Render as a five-field crontab entry."""
    text = _five_field_text(schedule, VIXIE_DOW_SPEC, "vixie cron")
    _seconds_caveat(schedule, "vixie cron", text)
    caveats = _day_caveats(schedule)
    if schedule.tz:
        caveats.append(
            f"vixie cron has no timezone field: put `CRON_TZ={schedule.tz}` on a line above the entry "
            "(Vixie and Debian cron), or run the job under `TZ=` itself."
        )
    return text, tuple(caveats)


def render_k8s(schedule: Schedule) -> tuple[str, tuple[str, ...]]:
    """Render as a Kubernetes CronJob `spec.schedule`."""
    text = _five_field_text(schedule, K8S_DOW_SPEC, "Kubernetes CronJob")
    _seconds_caveat(schedule, "Kubernetes CronJob", text)
    caveats = _day_caveats(schedule)
    caveats.append(
        f"set `spec.timeZone: {schedule.tz}` on the CronJob (Kubernetes 1.27+)."
        if schedule.tz
        else "with no `spec.timeZone`, a CronJob runs in the kube-controller-manager's zone — usually but not "
        "always UTC. `CRON_TZ=`/`TZ=` inside `spec.schedule` is not supported."
    )
    return text, tuple(caveats)


def _day_fields(schedule: Schedule, dom_spec: FieldSpec, dow_spec: FieldSpec, dialect: str) -> tuple[str, str, str]:
    """The day-of-month and day-of-week text for a dialect that demands a `?`."""
    dom_open, dow_open = is_open(schedule.dom), is_open(schedule.dow)
    if not dom_open and not dow_open:
        raise NotExpressibleError(
            f"{dialect} requires `?` in exactly one of day-of-month and day-of-week, so it cannot restrict both. "
            "Cron reads this as day-of-month OR day-of-week; there is no single "
            f"{dialect} expression with that meaning."
        )
    if dom_open and dow_open:
        return "*", "?", STAR_TO_QUESTION_CAVEAT
    if dow_open:
        return render_field(schedule.dom, dom_spec), "?", ""
    return "?", render_field(schedule.dow, dow_spec), ""


def _reject_eventbridge_specials(schedule: Schedule) -> None:
    for term in _specials(schedule.dom):
        if isinstance(term, LastDom) and term.offset:
            raise NotExpressibleError("EventBridge documents `L` only as the last day of the month; `L-n` is Quartz")
        if isinstance(term, NearestWeekday) and term.day is None:
            raise NotExpressibleError("EventBridge documents `W` only after a day number; `LW` is Quartz")
    dow = schedule.dow or ()
    if any(isinstance(term, NthDow) for term in dow) and len(dow) > 1:
        raise NotExpressibleError(
            "EventBridge allows only one expression in day-of-week when `#` is used: "
            f"{render_field(schedule.dow, EVENTBRIDGE_DOW_SPEC)} is read as several"
        )
    if any(getattr(term, "step", 1) > 1 for term in dow):
        raise NotExpressibleError("EventBridge's day-of-week field does not accept `/`; its wildcards are , - * ? L #")


def render_eventbridge(schedule: Schedule) -> tuple[str, tuple[str, ...]]:
    """Render as the body of an EventBridge `cron(...)` expression."""
    _reject_and_semantics(schedule, "EventBridge")
    _reject_eventbridge_specials(schedule)
    dom, dow, caveat = _day_fields(schedule, EVENTBRIDGE_DOM_SPEC, EVENTBRIDGE_DOW_SPEC, "EventBridge")
    year = render_field(schedule.year, EVENTBRIDGE_YEAR_SPEC)
    minute = render_field(schedule.minute, MINUTE_SPEC)
    hour = render_field(schedule.hour, HOUR_SPEC)
    month = render_field(schedule.month, MONTH_SPEC)
    text = f"{minute} {hour} {dom} {month} {dow} {year}"
    _seconds_caveat(schedule, "EventBridge", text)
    caveats = [caveat] if caveat else []
    if schedule.tz:
        caveats.append(
            f"EventBridge rules fire in UTC; only EventBridge Scheduler takes a ScheduleExpressionTimezone "
            f"({schedule.tz}). A plain rule needs the offset folded into the hours field."
        )
    return text, tuple(caveats)


def render_quartz(schedule: Schedule) -> tuple[str, tuple[str, ...]]:
    """Render as a seven-field Quartz expression."""
    _reject_and_semantics(schedule, "Quartz")
    years = expand(schedule.year, YEAR_MIN, YEAR_MAX)
    if not is_open(schedule.year) and max(years) > QUARTZ_YEAR_SPEC.high:
        raise NotExpressibleError(f"Quartz years stop at {QUARTZ_YEAR_SPEC.high}; this schedule reaches {max(years)}")
    dom, dow, caveat = _day_fields(schedule, QUARTZ_DOM_SPEC, QUARTZ_DOW_SPEC, "Quartz")
    fields = (
        render_field(schedule.second, SECOND_SPEC),
        render_field(schedule.minute, MINUTE_SPEC),
        render_field(schedule.hour, HOUR_SPEC),
        dom,
        render_field(schedule.month, MONTH_SPEC),
        dow,
        render_field(schedule.year, QUARTZ_YEAR_SPEC),
    )
    caveats = [caveat] if caveat else []
    if schedule.tz:
        caveats.append(
            f"Quartz holds the timezone on the trigger, not in the expression: "
            f'call `.inTimeZone(TimeZone.getTimeZone("{schedule.tz}"))` on the CronScheduleBuilder.'
        )
    return " ".join(fields), tuple(caveats)


YEAR_WIDTH = 4
FIELD_WIDTH = 2


def _systemd_term(term: Term, spec: FieldSpec, width: int) -> str:
    if isinstance(term, Every):
        return "*" if term.step == 1 else f"{spec.low:0{width}d}/{term.step}"
    if isinstance(term, LastDom):
        return f"~{term.offset + 1:0{width}d}"
    if not isinstance(term, Span):  # pragma: no cover — callers reject L/W/# first
        raise NotExpressibleError(f"systemd OnCalendar cannot express {term!r}")
    text = f"{term.lo:0{width}d}" if term.hi is None else f"{term.lo:0{width}d}..{term.hi:0{width}d}"
    return f"{text}/{term.step}" if term.step > 1 else text


def _systemd_field(field: Field, spec: FieldSpec, width: int = FIELD_WIDTH) -> str:
    if field is None:
        return "*"
    return ",".join(_systemd_term(term, spec, width) for term in field)


def _systemd_dow(field: Field) -> str:
    names: list[str] = []
    for term in field or ():
        if isinstance(term, Every):
            return ""
        if not isinstance(term, Span):  # pragma: no cover — rejected before we get here
            raise NotExpressibleError(f"systemd OnCalendar cannot express {term!r}")
        names.append(_systemd_dow_span(term))
    return ",".join(names)


def _systemd_dow_span(term: Span) -> str:
    if term.hi is None:
        return SYSTEMD_DOW_NAMES[term.lo]
    if term.lo > term.hi:
        wrapped = list(range(term.lo, DAYS_IN_WEEK)) + list(range(term.hi + 1))
        return ",".join(SYSTEMD_DOW_NAMES[day] for day in wrapped)
    if term.step > 1:
        return ",".join(SYSTEMD_DOW_NAMES[day] for day in range(term.lo, term.hi + 1, term.step))
    return f"{SYSTEMD_DOW_NAMES[term.lo]}..{SYSTEMD_DOW_NAMES[term.hi]}"


def _reject_systemd_specials(schedule: Schedule) -> None:
    for term in _specials(schedule.dow):
        raise NotExpressibleError(
            "systemd OnCalendar has no nth-weekday or last-weekday syntax: it cannot express "
            f"{_render_term(term, QUARTZ_DOW_SPEC)}"
        )
    for term in _specials(schedule.dom):
        if not isinstance(term, LastDom):
            raise NotExpressibleError(
                "systemd OnCalendar has no nearest-weekday syntax: it cannot express "
                f"{_render_term(term, QUARTZ_DOM_SPEC)}"
            )


def render_systemd(schedule: Schedule) -> tuple[str, tuple[str, ...]]:
    """Render as a systemd ``OnCalendar=`` value."""
    _reject_systemd_specials(schedule)
    day_spec = "-".join(
        (
            _systemd_field(schedule.year, YEAR_SPEC, YEAR_WIDTH),
            _systemd_field(schedule.month, MONTH_SPEC),
            _systemd_field(schedule.dom, SYSTEMD_DOM_SPEC),
        )
    )
    clock = ":".join(
        (
            _systemd_field(schedule.hour, HOUR_SPEC),
            _systemd_field(schedule.minute, MINUTE_SPEC),
            _systemd_field(schedule.second, SECOND_SPEC),
        )
    )
    weekday = _systemd_dow(schedule.dow)
    text = " ".join(part for part in (weekday, day_spec, clock, schedule.tz or "") if part)

    if schedule.day_match == "or" and not is_open(schedule.dom) and not is_open(schedule.dow):
        raise NotExpressibleError(
            "cron fires when day-of-month OR day-of-week matches; `OnCalendar=` fires only when both match. "
            "No single OnCalendar line has the cron meaning — write one timer per day field, or move the test "
            "into the unit.",
            closest=text,
        )
    caveats: list[str] = []
    if schedule.dom is None or schedule.dow is None:
        caveats.append("`?` becomes `*`: systemd has no 'no specific value', it simply ANDs the two.")
    if not schedule.tz:
        caveats.append(
            "with no timezone suffix, `OnCalendar=` follows the system clock; add `Persistent=true` "
            "to `[Timer]` if a missed run should fire on the next boot."
        )
    return text, tuple(caveats)


# --- the registry ----------------------------------------------------------


@dataclass(frozen=True)
class Dialect:
    """One syntax: how to read it, how to write it, what to call it."""

    name: str
    label: str
    parse: Callable[[str], Schedule]
    render: Callable[[Schedule], tuple[str, tuple[str, ...]]]


DIALECTS: dict[str, Dialect] = {
    "vixie": Dialect("vixie", "vixie cron (5 fields)", parse_vixie, render_vixie),
    "k8s": Dialect("k8s", "Kubernetes CronJob", parse_k8s, render_k8s),
    "eventbridge": Dialect("eventbridge", "AWS EventBridge (6 fields)", parse_eventbridge, render_eventbridge),
    "quartz": Dialect("quartz", "Quartz (7 fields)", parse_quartz, render_quartz),
    "systemd": Dialect("systemd", "systemd OnCalendar", parse_systemd, render_systemd),
}
ALIASES = {
    "cron": "vixie",
    "crontab": "vixie",
    "unix": "vixie",
    "kubernetes": "k8s",
    "cronjob": "k8s",
    "aws": "eventbridge",
    "oncalendar": "systemd",
    "timer": "systemd",
}


def resolve(name: str) -> Dialect:
    """Look a dialect up by name or alias."""
    key = ALIASES.get(name.strip().lower(), name.strip().lower())
    if key not in DIALECTS:
        known = ", ".join(sorted(DIALECTS))
        raise DialectError(f"unknown dialect {name!r}; known dialects are {known}")
    return DIALECTS[key]


@dataclass(frozen=True)
class Conversion:
    """One expression, read in one dialect and written in another."""

    source: Dialect
    target: Dialect
    source_expr: str
    target_expr: str
    schedule: Schedule
    target_schedule: Schedule
    caveats: tuple[str, ...]


def convert(expr: str, source: str, target: str) -> Conversion:
    """Convert `expr` between dialects, or raise `NotExpressibleError` rather than guess.

    The target expression is parsed back with the target's own parser, so the
    `Conversion` carries two schedules that a caller can run side by side —
    proof that the conversion says what it claims.
    """
    source_dialect, target_dialect = resolve(source), resolve(target)
    schedule = source_dialect.parse(expr)
    text, caveats = target_dialect.render(schedule)
    return Conversion(
        source=source_dialect,
        target=target_dialect,
        source_expr=expr.strip(),
        target_expr=text,
        schedule=schedule,
        target_schedule=target_dialect.parse(text),
        caveats=caveats,
    )


def describable(schedule: Schedule) -> tuple[str, bool] | None:
    """An expression cron-descriptor can read, and whether Sunday is 0 in it.

    Quartz says the most — seconds, years, `L`, `W`, `#` — so it is tried
    first; a schedule that restricts both day fields is not expressible there
    and falls back to the five-field form.
    """
    for render, dow_index_zero in ((render_quartz, False), (render_vixie, True)):
        try:
            return render(schedule)[0], dow_index_zero
        except NotExpressibleError:
            continue
    return None
