import json
from datetime import datetime
from zoneinfo import ZoneInfo

from cron_translate import describe, dst_warnings, main, phrase_to_cron, runs_between


def test_describe_simple_time():
    assert describe("0 3 * * *") == "at 03:00, every day"


def test_describe_weekdays():
    out = describe("*/15 9-17 * * 1-5")
    assert "every 15 minutes" in out
    assert "Monday" in out and "Friday" in out


def test_dst_warning_fires_for_us_eastern():
    # 02:30 daily hits the spring-forward gap in America/New_York
    assert dst_warnings("30 2 * * *", "America/New_York", runs=400)


def test_invalid_expression_exit_code():
    assert main(["not a cron"]) == 64


def test_cli_happy_path(capsys):
    assert main(["0 3 * * *", "--next", "1"]) == 0
    out = capsys.readouterr().out
    assert "Next 1 runs" in out


def test_phrase_weekday_at_time():
    assert phrase_to_cron("every weekday at 9am") == "0 9 * * 1-5"


def test_phrase_pm_and_minutes():
    assert phrase_to_cron("every day at 5:30pm") == "30 17 * * *"


def test_phrase_named_day():
    assert phrase_to_cron("every monday at 9am") == "0 9 * * 1"


def test_phrase_interval():
    assert phrase_to_cron("every 15 minutes") == "*/15 * * * *"
    assert phrase_to_cron("every 2 hours") == "0 */2 * * *"


def test_phrase_unrecognized_returns_none():
    assert phrase_to_cron("do the thing sometimes") is None


def test_cli_reverse_mode(capsys):
    assert main(["every weekday at 9am", "--next", "1"]) == 0
    out = capsys.readouterr().out
    assert "0 9 * * 1-5" in out


def test_runs_between_counts_daily_window():
    zone = ZoneInfo("UTC")
    start = datetime(2026, 7, 1, tzinfo=zone)
    end = datetime(2026, 7, 4, tzinfo=zone)
    runs = runs_between("0 0 * * *", start, end)
    assert [r.day for r in runs] == [2, 3, 4]


def test_cli_between(capsys):
    assert main(["0 0 * * *", "--between", "2026-07-01T00:00", "2026-07-03T00:00"]) == 0
    out = capsys.readouterr().out
    assert "Runs between" in out
    assert "2026-07-02" in out and "2026-07-03" in out


def test_cli_json_output(capsys):
    assert main(["0 3 * * *", "--next", "2", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["expression"] == "0 3 * * *"
    assert len(data["runs"]) == 2
    assert data["dst_warnings"] == []


def test_cli_json_invalid_expression(capsys):
    assert main(["not a cron", "--json"]) == 64
    data = json.loads(capsys.readouterr().out)
    assert "error" in data
