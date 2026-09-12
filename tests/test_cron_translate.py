import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from croniter import croniter

from cron_translate import (
    Translation,
    describe,
    dst_notes,
    dst_warnings,
    main,
    phrase_to_cron,
    runs_between,
    translate_phrase,
)


def test_describe_simple_time() -> None:
    # The wording is cron-descriptor's, not this repo's.
    assert describe("0 3 * * *") == "At 03:00"


def test_describe_weekdays() -> None:
    out = describe("*/15 9-17 * * 1-5")
    assert "Every 15 minutes" in out
    assert "Monday" in out
    assert "Friday" in out


def test_dst_warning_fires_for_us_eastern() -> None:
    # 02:30 daily hits the spring-forward gap in America/New_York
    assert dst_warnings("30 2 * * *", "America/New_York", runs=400)


def test_invalid_expression_exit_code() -> None:
    assert main(["not a cron"]) == 64


def test_invalid_expression_diagnostic_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["total nonsense"]) == 64
    captured = capsys.readouterr()
    assert captured.err.strip() == "cron-translate: invalid cron expression: 'total nonsense'"
    assert captured.out == ""


def test_cli_happy_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["0 3 * * *", "--next", "1"]) == 0
    out = capsys.readouterr().out
    assert "Next 1 runs" in out


def test_phrase_weekday_at_time() -> None:
    assert phrase_to_cron("every weekday at 9am") == "0 9 * * 1-5"


def test_phrase_pm_and_minutes() -> None:
    assert phrase_to_cron("every day at 5:30pm") == "30 17 * * *"


def test_phrase_named_day() -> None:
    assert phrase_to_cron("every monday at 9am") == "0 9 * * 1"


def test_phrase_interval() -> None:
    assert phrase_to_cron("every 15 minutes") == "*/15 * * * *"
    assert phrase_to_cron("every 2 hours") == "0 */2 * * *"


def test_phrase_unrecognized_returns_none() -> None:
    assert phrase_to_cron("do the thing sometimes") is None


def test_cli_reverse_mode(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["every weekday at 9am", "--next", "1"]) == 0
    out = capsys.readouterr().out
    assert "0 9 * * 1-5" in out


def test_runs_between_counts_daily_window() -> None:
    zone = ZoneInfo("UTC")
    start = datetime(2026, 7, 1, tzinfo=zone)
    end = datetime(2026, 7, 4, tzinfo=zone)
    runs = runs_between("0 0 * * *", start, end)
    assert [r.day for r in runs] == [2, 3, 4]


def test_cli_between(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["0 0 * * *", "--between", "2026-07-01T00:00", "2026-07-03T00:00"]) == 0
    out = capsys.readouterr().out
    assert "Runs between" in out
    assert "2026-07-02" in out
    assert "2026-07-03" in out


def test_cli_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["0 3 * * *", "--next", "2", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["expression"] == "0 3 * * *"
    assert len(data["runs"]) == 2
    assert data["dst_warnings"] == []


def test_cli_json_invalid_expression(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["not a cron", "--json"]) == 64
    data = json.loads(capsys.readouterr().out)
    assert "error" in data


# --- English phrases cron cannot express -----------------------------------


def _translated(phrase: str) -> Translation:
    """The translation for a phrase this tool is expected to recognise."""
    translation = translate_phrase(phrase)
    assert translation is not None
    return translation


def _note(phrase: str) -> str:
    """The 'here is what cron loses' note, which these phrases all carry."""
    note = _translated(phrase).note
    assert note is not None
    return note


def test_phrase_every_two_weeks_is_refused_with_a_reason() -> None:
    translation = _translated("every 2 weeks")
    assert translation.cron is None
    assert not translation.exact
    note = _note("every 2 weeks")
    assert "no week counter" in note
    assert "OnUnitActiveSec=2w" in note


def test_phrase_last_friday_offers_the_quartz_form() -> None:
    assert _translated("last friday of the month").cron is None
    note = _note("last friday of the month")
    assert "0 0 0 ? * 6L *" in note
    # The tempting wrong answer, named so nobody reaches for it.
    assert "ORs day-of-month against day-of-week" in note


def test_phrase_nth_weekday_offers_the_hash_form() -> None:
    assert "6#3" in _note("third friday of the month")


def test_phrase_last_day_of_month_offers_l_syntax() -> None:
    assert _translated("last day of the month").cron is None
    assert "0 0 0 L * ? *" in _note("last day of the month")


def test_phrase_uneven_minute_step_is_translated_but_flagged() -> None:
    translation = _translated("every 7 minutes")
    assert translation.cron == "*/7 * * * *"
    assert not translation.exact
    assert "restarts at the top of every hour" in _note("every 7 minutes")


def test_phrase_interval_longer_than_an_hour_offers_crontab_lines() -> None:
    assert _translated("every 90 minutes").cron is None
    note = _note("every 90 minutes")
    assert "0 0,3,6,9,12,15,18,21 * * *" in note
    assert "30 1,4,7,10,13,16,19,22 * * *" in note


def test_phrase_day_step_flags_the_month_boundary() -> None:
    assert _translated("every 3 days").cron == "0 0 */3 * *"
    assert "restarts on the 1st" in _note("every 3 days")


def test_phrase_even_steps_stay_exact() -> None:
    for phrase in ("every 15 minutes", "every 2 hours", "every 1 day", "every 6 months"):
        assert _translated(phrase).exact


def test_cli_reports_an_inexpressible_phrase(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["every 2 weeks"]) == 64
    assert "no week counter" in capsys.readouterr().err


def test_cli_runs_an_inexact_phrase_and_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["every 7 minutes", "--next", "1"]) == 0
    out = capsys.readouterr().out
    assert "*/7 * * * *" in out
    assert "restarts at the top of every hour" in out


# --- DST on the runs themselves --------------------------------------------


def test_spring_forward_run_is_flagged(capsys: pytest.CaptureFixture[str]) -> None:
    # 02:30 does not exist on 14 March 2027 in New York.
    assert main(["30 2 * * *", "--tz", "America/New_York", "--between", "2027-03-13T00:00", "2027-03-15T00:00"]) == 0
    out = capsys.readouterr().out
    assert "does not exist (spring forward)" in out
    assert out.count("⚠") == 1


def test_fall_back_run_is_flagged(capsys: pytest.CaptureFixture[str]) -> None:
    # 01:30 happens twice on 7 November 2027 in New York, and croniter emits
    # both -- so both lines carry the flag.
    assert main(["30 1 * * *", "--tz", "America/New_York", "--between", "2027-11-06T00:00", "2027-11-08T00:00"]) == 0
    out = capsys.readouterr().out
    assert out.count("happens twice (fall back)") == 2


def test_no_dst_check_suppresses_the_run_flags(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["30 2 * * *", "--tz", "America/New_York", "--between", "2027-03-13T00:00", "2027-03-15T00:00"]
    assert main([*args, "--no-dst-check"]) == 0
    assert "⚠" not in capsys.readouterr().out


def test_utc_runs_are_never_flagged() -> None:
    runs = runs_between(
        "30 2 * * *", datetime(2027, 3, 13, tzinfo=ZoneInfo("UTC")), datetime(2027, 3, 16, tzinfo=ZoneInfo("UTC"))
    )
    assert dst_notes(runs, lambda wall: croniter.match("30 2 * * *", wall)) == [None, None, None]


def test_json_carries_the_per_run_dst_notes(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(["30 2 * * *", "--tz", "America/New_York", "--json", "--between", "2027-03-13T00:00", "2027-03-15T00:00"])
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["run_dst"][0] is None
    assert "spring forward" in data["run_dst"][1]


# --- the convert subcommand ------------------------------------------------


def test_convert_prints_both_expressions_and_both_run_lists(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--from", "quartz", "--to", "eventbridge", "0 0 12 ? * MON-FRI *"]) == 0
    out = capsys.readouterr().out
    assert "0 12 ? * 2-6 *" in out
    assert "both dialects on the same clock" in out


def test_convert_refuses_an_impossible_pair(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--from", "quartz", "--to", "vixie", "30 0 12 ? * 6#3 *"]) == 65
    err = capsys.readouterr().err
    assert "cannot convert to vixie" in err


def test_convert_offers_the_closest_expression_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--from", "quartz", "--to", "vixie", "30 0 12 ? * MON-FRI *"]) == 65
    err = capsys.readouterr().err
    assert "NOT equivalent" in err
    assert "0 12 * * 1-5" in err


def test_convert_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--from", "vixie", "--to", "systemd", "0 9 * * 1-5", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["target"] == "Mon..Fri *-*-* 09:00:00"
    assert data["agree"] is True
    assert data["source_runs"] == data["target_runs"]


def test_convert_json_impossible(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--from", "quartz", "--to", "vixie", "0 0 12 ? * 6#3 *", "--json"]) == 65
    data = json.loads(capsys.readouterr().out)
    assert data["impossible"] is True


def test_convert_rejects_an_unknown_dialect(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--from", "vixie", "--to", "cronicle", "0 9 * * 1-5"]) == 64
    assert "unknown dialect" in capsys.readouterr().err


def test_convert_describes_the_schedule_once(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--from", "systemd", "--to", "quartz", "Mon..Fri *-*-* 09:00:00"]) == 0
    assert "At 09:00, Monday through Friday" in capsys.readouterr().out


# --- regressions -----------------------------------------------------------


def test_croniter_seconds_field_is_moved_to_the_front_for_the_description() -> None:
    # croniter reads a sixth field as seconds after the weekday;
    # cron-descriptor reads it as seconds first. Handed one as the other it
    # described `0 12 * * 1 0` as "only on Sunday, only in January".
    assert describe("0 12 * * 1 0", seconds_last=True) == "At 12:00, only on Monday"
    assert describe("0 12 * * 1 30", seconds_last=True) == "At 12:00:30, only on Monday"
    assert describe("0 12 * * 1 0 2027", seconds_last=True) == "At 12:00, only on Monday, only in 2027"


def test_quartz_layout_is_left_alone() -> None:
    assert describe("30 0 12 ? * 6#3 *", dow_index_zero=False) == "At 12:00:30, on the third Friday of the month"


def test_cli_describes_a_six_field_expression_correctly(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["0 12 * * 1 0", "--next", "1"]) == 0
    assert "only on Monday" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("phrase", "unit"),
    [("every 36 hours", "36h"), ("every 40 days", "40d"), ("every 18 months", "18months")],
)
def test_intervals_beyond_a_field_have_no_cron_answer(phrase: str, unit: str) -> None:
    # `*/36` in a 0-23 field and `*/40` in a 1-31 one are accepted by croniter
    # and mean something else entirely -- daily and "the 1st", respectively.
    assert _translated(phrase).cron is None
    assert f"OnUnitActiveSec={unit}" in _note(phrase)


def test_an_interval_that_does_not_tile_a_day_offers_no_crontab_lines() -> None:
    # 2880 minutes is two days: no set of crontab entries repeats it.
    assert _translated("every 2880 minutes").cron is None
    assert "none of its fields can count 2880 minutes" in _note("every 2880 minutes")


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [("every 24 hours", "0 0 * * *"), ("every 12 months", "0 0 1 1 *"), ("every 90 minutes", None)],
)
def test_interval_boundaries(phrase: str, expected: str | None) -> None:
    assert _translated(phrase).cron == expected


def test_every_translated_phrase_is_valid_cron() -> None:
    phrases = [
        f"every {n} {unit}"
        for n in (1, 2, 3, 7, 12, 24, 36, 40, 59, 60, 90, 2880)
        for unit in ("minutes", "hours", "days", "weeks", "months")
    ]
    for phrase in phrases:
        cron = _translated(phrase).cron
        assert cron is None or croniter.is_valid(cron), f"{phrase} -> {cron}"


def test_the_cli_reads_the_day_fields_the_way_the_crontab_will(capsys: pytest.CaptureFixture[str]) -> None:
    # croniter's default ORs the day fields; the crontab on the box ANDs them
    # when either is written with a star. The CLI has to agree with the box.
    assert main(["0 9 */10 * 1-5", "--between", "2026-09-12T00:00", "2026-11-30T00:00"]) == 0
    out = capsys.readouterr().out
    assert "2026-09-21" in out  # the 21st, and a Monday
    assert "2026-11-01" not in out  # the 1st, but a Sunday
    assert "2026-09-14" not in out  # a Monday, but not a 1st/11th/21st/31st
    assert "Runs between 2026-09-12 00:00 UTC and 2026-11-30 00:00 UTC: 4" in out


def test_a_day_rule_without_a_star_accepts_either_field(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["0 9 1 * 1", "--between", "2026-09-12T00:00", "2026-09-30T00:00"]) == 0
    out = capsys.readouterr().out
    assert "2026-09-14" in out  # a Monday
    assert "2026-09-21" in out  # a Monday
