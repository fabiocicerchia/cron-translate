@domain:dst-safety @area:per-run-flags @from:cron-translate/cron-translate
Feature: Flagging runs in a skipped or repeated hour
  Marks the exact runs that daylight saving will skip or repeat, so operators can fix the schedule.

  Background:
    Given the operator's zone is America/New_York

  @id:dst-safety.per-run-flags.001 @rule:dst.flags.spring-forward-run @verified @source:cron_translate.py#dst_notes @test:tests/test_cron_translate.py#test_spring_forward_run_is_flagged @test:tests/test_cron_translate.py#test_json_carries_the_per_run_dst_notes
  Scenario: A run in the spring-forward gap is flagged as skipped or shifted
    Given the schedule "30 2 * * *"
    When the operator lists its runs between 2027-03-13T00:00 and 2027-03-15T00:00
    Then the 2027-03-14 run line ends with "⚠ DST: this wall-clock time does not exist (spring forward) — the run is skipped or shifted"
    And the 2027-03-13 run line carries no flag

  @id:dst-safety.per-run-flags.002 @rule:dst.flags.fall-back-run @verified @source:cron_translate.py#dst_notes @test:tests/test_cron_translate.py#test_fall_back_run_is_flagged
  Scenario: A run in the repeated fall-back hour is listed twice and both are flagged
    Given the schedule "30 1 * * *"
    When the operator lists its runs between 2027-11-06T00:00 and 2027-11-08T00:00
    Then two run lines for 01:30 on 2027-11-07 appear
    And both end with "⚠ DST: this wall-clock time happens twice (fall back) — the run may fire twice"

  @id:dst-safety.per-run-flags.003 @rule:dst.flags.never-in-utc @verified @source:cron_translate.py#dst_notes @test:tests/test_cron_translate.py#test_utc_runs_are_never_flagged
  Scenario: Runs in UTC are never flagged
    Given the schedule "30 2 * * *" in UTC instead
    When the operator lists its runs between 2027-03-13T00:00 and 2027-03-16T00:00
    Then no run line carries a DST flag
