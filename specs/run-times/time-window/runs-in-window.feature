@domain:run-times @area:time-window @from:cron-translate/cron-translate
Feature: Listing runs within a time window
  Lets operators see every run a schedule makes between two moments, e.g. around a maintenance or DST date.

  @id:run-times.time-window.001 @rule:runs.window.lists-runs-in-window @verified @source:cron_translate.py#runs_between @test:tests/test_cron_translate.py#test_cli_between @test:tests/test_cron_translate.py#test_runs_between_counts_daily_window
  Scenario: Every run inside the window is listed with a count, including one exactly at the end
    Given the schedule "0 0 * * *"
    When the operator lists its runs between 2026-07-01T00:00 and 2026-07-03T00:00
    Then the heading reads "Runs between 2026-07-01 00:00 UTC and 2026-07-03 00:00 UTC: 2"
    And the runs "2026-07-02 00:00 UTC" and "2026-07-03 00:00 UTC" are listed
    And no run line carries a countdown

  @id:run-times.time-window.002 @rule:runs.window.start-instant-excluded @verified @source:cron_translate.py#runs_between @test:tests/test_cron_translate.py#test_runs_between_counts_daily_window @questionable
  Scenario: A run exactly at the window's start is not listed
    Given the schedule "0 0 * * *"
    When the operator lists its runs between 2026-07-01T00:00 and 2026-07-04T00:00
    Then the runs on 2026-07-02, 2026-07-03 and 2026-07-04 are listed
    And the run at 2026-07-01 00:00 is not listed

  @id:run-times.time-window.003 @rule:runs.window.times-read-in-chosen-zone @inferred @source:cron_translate.py#_parse_dt
  Scenario: Window times without an offset are read on the chosen zone's clock
    Given the schedule "30 2 * * *"
    When the operator lists its runs in America/New_York between 2027-03-13T00:00 and 2027-03-15T00:00
    Then the heading reads "Runs between 2027-03-13 00:00 EST and 2027-03-15 00:00 EDT: 2"
