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
