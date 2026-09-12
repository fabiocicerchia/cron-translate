"""Dialect conversion: every pair, and the pairs that must refuse."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cron_dialects import (
    DIALECTS,
    DialectError,
    NotExpressibleError,
    convert,
    matches,
    next_runs,
    resolve,
)
from cron_translate import DOUBLED, SKIPPED, describe_schedule, dst_notes

UTC = ZoneInfo("UTC")
NEW_YORK = ZoneInfo("America/New_York")
CLOCK = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)

# One schedule -- weekdays at 09:00 -- written in each dialect's canonical
# form. Every dialect can say it, so every ordered pair is a real conversion
# with a known right answer on both sides.
PLAIN = {
    "vixie": "0 9 * * 1-5",
    "k8s": "0 9 * * 1-5",
    "eventbridge": "0 9 ? * 2-6 *",
    "quartz": "0 0 9 ? * 2-6 *",
    "systemd": "Mon..Fri *-*-* 09:00:00",
}


def test_plain_covers_every_registered_dialect() -> None:
    # A dialect added without a PLAIN entry would silently drop out of the
    # matrix below instead of failing.
    assert set(PLAIN) == set(DIALECTS)


@pytest.mark.parametrize("target", sorted(PLAIN))
@pytest.mark.parametrize("source", sorted(PLAIN))
def test_every_pair_converts_to_the_canonical_form(source: str, target: str) -> None:
    conversion = convert(PLAIN[source], source, target)
    assert conversion.target_expr == PLAIN[target]


@pytest.mark.parametrize("target", sorted(PLAIN))
@pytest.mark.parametrize("source", sorted(PLAIN))
def test_every_pair_agrees_on_the_next_runs(source: str, target: str) -> None:
    # The target text is parsed back with the target's own parser, so this
    # compares two independently built schedules rather than one twice.
    conversion = convert(PLAIN[source], source, target)
    assert next_runs(conversion.schedule, CLOCK, 5) == next_runs(conversion.target_schedule, CLOCK, 5)


def test_weekday_numbering_survives_the_round_trip() -> None:
    # Monday is 1 in vixie and 2 in Quartz/EventBridge. Getting this wrong
    # shifts every schedule by a day and still looks plausible.
    runs = next_runs(convert("0 9 * * 1", "vixie", "quartz").target_schedule, CLOCK, 1)
    assert runs[0].strftime("%A") == "Monday"


def test_sunday_seven_is_sunday_zero() -> None:
    assert convert("0 0 * * 7", "vixie", "k8s").target_expr == "0 0 * * 0"


def test_quartz_year_field_is_optional() -> None:
    assert convert("0 0 9 ? * 2-6", "quartz", "vixie").target_expr == "0 9 * * 1-5"


def test_macro_expands() -> None:
    assert convert("@daily", "vixie", "quartz").target_expr == "0 0 0 * * ? *"


def test_eventbridge_cron_wrapper_is_accepted() -> None:
    assert convert("cron(0 9 ? * 2-6 *)", "eventbridge", "vixie").target_expr == "0 9 * * 1-5"


def test_aliases_resolve() -> None:
    assert resolve("aws").name == "eventbridge"
    assert resolve("kubernetes").name == "k8s"
    assert resolve("OnCalendar").name == "systemd"


# --- the pairs that must refuse --------------------------------------------

# (source dialect, expression, target dialect, a fragment of the reason)
IMPOSSIBLE = [
    ("quartz", "30 0 9 ? * 2-6 *", "vixie", "seconds"),
    ("quartz", "30 0 9 ? * 2-6 *", "k8s", "seconds"),
    ("quartz", "30 0 9 ? * 2-6 *", "eventbridge", "seconds"),
    ("quartz", "0 0 9 ? * 6#3 *", "vixie", "#"),
    ("quartz", "0 0 9 ? * 6#3 *", "k8s", "#"),
    ("quartz", "0 0 9 ? * 6#3 *", "systemd", "nth-weekday"),
    ("quartz", "0 0 9 L * ? *", "vixie", "L"),
    ("quartz", "0 0 9 L * ? *", "k8s", "L"),
    ("quartz", "0 0 9 15W * ? *", "vixie", "W"),
    ("quartz", "0 0 9 15W * ? *", "k8s", "W"),
    ("quartz", "0 0 9 15W * ? *", "systemd", "nearest-weekday"),
    ("quartz", "0 0 9 L-3 * ? *", "eventbridge", "L-n"),
    ("quartz", "0 0 9 LW * ? *", "eventbridge", "LW"),
    ("quartz", "0 0 9 LW * ? *", "systemd", "nearest-weekday"),
    ("quartz", "0 0 9 ? * 2-6 2027", "vixie", "year"),
    ("quartz", "0 0 9 ? * 2-6 2027", "k8s", "year"),
    ("eventbridge", "0 9 ? * 2-6 2150", "quartz", "2099"),
    ("quartz", "0 0 9 ? * 2-6/2 *", "eventbridge", "does not accept `/`"),
    ("quartz", "0 0 9 ? * 6#3,2 *", "eventbridge", "only one expression"),
    # Both day fields restricted: cron ORs them, and the `?` dialects have no
    # way to write that at all.
    ("vixie", "0 9 1 * 1-5", "eventbridge", "`?` in exactly one"),
    ("vixie", "0 9 1 * 1-5", "quartz", "`?` in exactly one"),
    ("vixie", "0 9 1 * 1-5", "systemd", "OR"),
    # ...and the mirror image: systemd ANDs them, which no cron dialect says.
    ("systemd", "Mon..Fri *-*-01 09:00:00", "vixie", "ANDs"),
    ("systemd", "Mon..Fri *-*-01 09:00:00", "k8s", "ANDs"),
    ("systemd", "Mon..Fri *-*-01 09:00:00", "eventbridge", "ANDs"),
    ("systemd", "Mon..Fri *-*-01 09:00:00", "quartz", "ANDs"),
]


@pytest.mark.parametrize(("source", "expr", "target", "fragment"), IMPOSSIBLE)
def test_impossible_conversions_refuse_and_say_why(source: str, expr: str, target: str, fragment: str) -> None:
    with pytest.raises(NotExpressibleError) as raised:
        convert(expr, source, target)
    assert fragment in raised.value.reason


def test_impossible_conversion_offers_the_closest_expression() -> None:
    with pytest.raises(NotExpressibleError) as raised:
        convert("30 0 9 ? * 2-6 *", "quartz", "vixie")
    # Not equivalent -- it drops the :30 -- which is exactly why it is offered
    # as `closest` rather than returned as the conversion.
    assert raised.value.closest == "0 9 * * 1-5"


@pytest.mark.parametrize(
    ("source", "expr"),
    [
        ("vixie", "0 9 * * 1-5 *"),
        ("vixie", "@reboot"),
        ("k8s", "0 0 * * 7"),
        ("eventbridge", "0 9 * * * *"),
        ("eventbridge", "0 9 ? * 2-6/2 *"),
        ("quartz", "0 0 9 ? * ? *"),
        ("quartz", "0 9 ? * 2-6"),
        ("systemd", "nonsense"),
    ],
)
def test_invalid_source_expressions_are_rejected(source: str, expr: str) -> None:
    with pytest.raises(DialectError):
        convert(expr, source, "vixie")


def test_unknown_dialect_is_rejected() -> None:
    with pytest.raises(DialectError, match="unknown dialect"):
        convert("0 9 * * 1-5", "vixie", "cronicle")


# --- the schedule engine ---------------------------------------------------


def _days(expr: str, source: str, count: int = 3) -> list[str]:
    return [run.strftime("%Y-%m-%d") for run in next_runs(resolve(source).parse(expr), CLOCK, count)]


def test_last_day_of_month() -> None:
    assert _days("0 0 12 L * ? *", "quartz") == ["2026-09-30", "2026-10-31", "2026-11-30"]


def test_days_before_the_last_day() -> None:
    assert _days("0 0 12 L-3 * ? *", "quartz") == ["2026-09-27", "2026-10-28", "2026-11-27"]


def test_nth_weekday_of_month() -> None:
    # The third Friday.
    assert _days("0 0 12 ? * 6#3 *", "quartz") == ["2026-09-18", "2026-10-16", "2026-11-20"]


def test_last_weekday_of_month() -> None:
    assert _days("0 0 12 ? * 6L *", "quartz") == ["2026-09-25", "2026-10-30", "2026-11-27"]


def test_nearest_weekday_never_leaves_the_month() -> None:
    # 1 November 2026 is a Sunday, so `1W` moves forward to Monday the 2nd
    # rather than back into October.
    assert "2026-11-02" in _days("0 0 12 1W * ? *", "quartz", count=3)


def test_last_weekday_of_the_month() -> None:
    # 31 October 2026 is a Saturday; the last weekday is Friday the 30th.
    assert _days("0 0 12 LW * ? *", "quartz", count=2) == ["2026-09-30", "2026-10-30"]


def test_systemd_ands_weekday_and_date() -> None:
    # The 1st that is also a Monday -- far rarer than either on its own.
    assert _days("Mon *-*-01 09:00:00", "systemd", count=2) == ["2027-02-01", "2027-03-01"]


def test_cron_ors_weekday_and_date() -> None:
    # The same two fields in vixie: every Monday *and* every 1st.
    assert _days("0 9 1 * 1", "vixie", count=3) == ["2026-09-14", "2026-09-21", "2026-09-28"]


def test_year_field_limits_the_walk() -> None:
    assert next_runs(resolve("quartz").parse("0 0 12 1 1 ? 2028"), CLOCK, 5) == [
        datetime(2028, 1, 1, 12, 0, tzinfo=UTC)
    ]


def test_systemd_repetition_round_trips() -> None:
    # The hour range is spelled out rather than left as Quartz's `0/6`, so the
    # same text is valid in the five-field dialects too.
    assert convert("*-*-* 00/6:00:00", "systemd", "quartz").target_expr == "0 0 0-23/6 * * ? *"


def test_systemd_last_day_uses_tilde() -> None:
    assert convert("0 0 12 L * ? *", "quartz", "systemd").target_expr == "*-*-~01 12:00:00"


def test_systemd_shorthand() -> None:
    assert convert("daily", "systemd", "vixie").target_expr == "0 0 * * *"


def test_timezone_survives_from_systemd_as_a_caveat() -> None:
    conversion = convert("Mon..Fri *-*-* 09:00:00 Europe/Rome", "systemd", "k8s")
    assert conversion.target_expr == "0 9 * * 1-5"
    assert any("spec.timeZone: Europe/Rome" in caveat for caveat in conversion.caveats)


def test_question_mark_conversion_carries_a_caveat() -> None:
    conversion = convert("0 9 ? * 2-6 *", "eventbridge", "vixie")
    assert any("`?`" in caveat for caveat in conversion.caveats)


# --- DST, on the schedule engine's own runs --------------------------------


def _notes(expr: str, source: str, start: datetime, count: int) -> list[str | None]:
    schedule = resolve(source).parse(expr)
    runs = next_runs(schedule, start, count)
    return dst_notes(runs, lambda wall: matches(schedule, wall))


def test_gap_run_is_reported_as_skipped_not_doubled() -> None:
    # A wall-clock time inside the spring-forward gap also has two different
    # offsets across `fold`, so an ambiguity test alone calls it a fall-back.
    notes = _notes("0 30 2 * * ? *", "quartz", datetime(2027, 3, 12, tzinfo=NEW_YORK), 4)
    assert notes == [None, None, SKIPPED, None]


def test_repeated_hour_is_reported_as_doubled() -> None:
    notes = _notes("0 30 1 * * ? *", "quartz", datetime(2027, 11, 5, tzinfo=NEW_YORK), 4)
    assert notes == [None, None, DOUBLED, None]


def test_utc_never_flags_a_run() -> None:
    assert _notes("0 30 2 * * ? *", "quartz", datetime(2027, 3, 12, tzinfo=UTC), 4) == [None] * 4


# --- regressions -----------------------------------------------------------


def test_systemd_time_field_is_not_mistaken_for_a_timezone() -> None:
    # `*:0/15:00` contains a slash, and a loose zone test swallowed the whole
    # time field -- turning "every 15 minutes" into "daily at midnight".
    schedule = resolve("systemd").parse("*-*-* *:0/15:00")
    assert schedule.tz is None
    assert convert("*-*-* *:0/15:00", "systemd", "vixie").target_expr == "0-59/15 * * * *"


def test_real_timezone_suffix_still_parses() -> None:
    assert resolve("systemd").parse("Mon..Fri *-*-* 09:00:00 Europe/Rome").tz == "Europe/Rome"
    assert resolve("systemd").parse("*-*-* 09:00:00 UTC").tz == "UTC"


def test_stepped_weekday_is_not_dropped_by_systemd() -> None:
    assert convert("0 0 * * */2", "vixie", "systemd").target_expr == "Sun,Tue,Thu,Sat *-*-* 00:00:00"


def test_open_ended_weekday_step_keeps_its_step_in_systemd() -> None:
    assert convert("0 0 0 ? * 2/2", "quartz", "systemd").target_expr == "Mon,Wed,Fri *-*-* 00:00:00"


@pytest.mark.parametrize("expr", ["0 0 * * 0-7", "0 0 * * 0-6"])
def test_whole_week_range_covers_every_day(expr: str) -> None:
    # Reducing both ends modulo 7 first collapsed `0-7` to "Sunday to Sunday".
    assert convert(expr, "vixie", "quartz").target_expr == "0 0 0 ? * 1-7 *"
    assert len({run.strftime("%A") for run in next_runs(resolve("vixie").parse(expr), CLOCK, 7)}) == 7


def test_whole_week_range_is_still_a_restricted_field() -> None:
    # cron's OR rule keys off the literal `*`, not off the set of days: with
    # day-of-month restricted too, `0-7` makes the entry fire every day. Turning
    # it into `*` would have made it fire only on the 1st.
    assert _days("0 9 1 * 0-7", "vixie", count=3) == ["2026-09-12", "2026-09-13", "2026-09-14"]
    assert _days("0 9 1 * *", "vixie", count=2) == ["2026-10-01", "2026-11-01"]


def test_wrapping_weekday_range_keeps_its_step() -> None:
    # FRI-MON stepping by two is Friday and Sunday, not all four days.
    assert convert("0 9 * * 5-1/2", "vixie", "quartz").target_expr == "0 0 9 ? * 6,1 *"
    assert convert("0 9 * * 5-1/2", "vixie", "systemd").target_expr == "Fri,Sun *-*-* 09:00:00"


def test_wrapping_weekday_range_without_a_step() -> None:
    assert convert("0 0 * * 5-1", "vixie", "eventbridge").target_expr == "0 0 ? * 6,7,1,2 *"


def test_open_ended_step_renders_as_a_range_for_five_field_dialects() -> None:
    # `5/10` is Quartz's spelling; vixie only documents a step after a range
    # or a star, so the range is spelled out.
    assert convert("0 0 0 5/10 * ? *", "quartz", "vixie").target_expr == "0 0 5-31/10 * *"


def test_a_year_past_the_quartz_ceiling_is_still_describable() -> None:
    # `describable` must not inherit Quartz's 2099 limit: cron-descriptor has
    # no such limit, and the caller only wants a layout it can read.
    assert "2150" in describe_schedule(resolve("eventbridge").parse("0 9 ? * 2-6 2150"))


# --- cron's day rule: the star, not the set of days ------------------------


def test_star_step_day_of_month_ands_rather_than_ors() -> None:
    # Vixie and ISC cron AND the two day fields whenever either is written
    # with a star, `*/10` included. Reading this as OR puts a run on every
    # weekday as well as every tenth day.
    # The 1st, 11th, 21st and 31st that are also weekdays: the 21st (Mon),
    # 1 Oct (Thu), 21 Oct (Wed), 11 Nov (Wed). No 31 September, and 1 Nov is
    # a Sunday, so both are skipped.
    assert _days("0 9 */10 * 1-5", "vixie", count=4) == ["2026-09-21", "2026-10-01", "2026-10-21", "2026-11-11"]


def test_no_star_still_ors() -> None:
    assert _days("0 9 1 * 1", "vixie", count=3) == ["2026-09-14", "2026-09-21", "2026-09-28"]


def test_full_week_day_of_week_against_a_star_step() -> None:
    # `1-7` matches every day but is not a star, so the star in day-of-month
    # decides: the 1st, 11th, 21st and 31st, every one of which is some day of
    # the week.
    assert _days("0 9 */10 * 1-7", "vixie", count=4) == ["2026-09-21", "2026-10-01", "2026-10-11", "2026-10-21"]


def test_full_week_day_of_week_without_a_star_ors_to_every_day() -> None:
    assert _days("0 9 1 * 0-7", "vixie", count=3) == ["2026-09-12", "2026-09-13", "2026-09-14"]


def test_a_starred_day_field_makes_systemd_reachable() -> None:
    # Under the star rule this vixie entry already means AND, which is the
    # only thing `OnCalendar=` can say -- so it converts instead of refusing.
    assert convert("0 9 */10 * 1-5", "vixie", "systemd").target_expr == "Mon..Fri *-*-01/10 09:00:00"


def test_without_a_star_systemd_still_refuses() -> None:
    with pytest.raises(NotExpressibleError, match="OR"):
        convert("0 9 1 * 1-5", "vixie", "systemd")


def test_horizon_reaches_far_enough_for_a_sparse_schedule() -> None:
    # A leap-day schedule needs four years per run; a five-year horizon
    # silently returned two of the three asked for.
    assert _days("0 0 0 29 2 ? *", "quartz", count=3) == ["2028-02-29", "2032-02-29", "2036-02-29"]
