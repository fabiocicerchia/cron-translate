@domain:dst-safety @area:transition-warnings @from:cron-translate/cron-translate
Feature: Warning about upcoming DST transitions
  Warns operators before a schedule crosses a daylight-saving change in their zone.

  @id:dst-safety.transition-warnings.001 @rule:dst.warnings.transition-ahead @verified @source:cron_translate.py#dst_warnings @test:tests/test_cron_translate.py#test_dst_warning_fires_for_us_eastern @questionable
  Scenario: A DST change between two upcoming runs is warned about, at most three times
    Given a daylight-saving change in America/New_York falls between two of the schedule's next 100 runs
    When the operator describes "0 2 * * 0" in America/New_York
    Then after the runs, a line reads "⚠ DST transition between <run before> and <run after>: a run may be skipped (spring forward) or duplicated (fall back)"
    And no more than 3 such lines appear

  @id:dst-safety.transition-warnings.002 @rule:dst.warnings.lookahead-limited-to-100-runs @inferred @source:cron_translate.py#dst_warnings @questionable
  Scenario: A DST change more than 100 runs away is not warned about
    Given today is 2026-11-07 and the next America/New_York change is 2027-03-14
    When the operator describes "30 2 * * *" in America/New_York
    Then no "DST transition" warning is shown

  @id:dst-safety.transition-warnings.003 @rule:dst.warnings.skipped-for-utc-and-windows @verified @source:cron_translate.py#_describe_main @test:tests/test_cron_translate.py#test_cli_json_output @test:tests/test_cron_translate.py#test_spring_forward_run_is_flagged
  Scenario Outline: Transition warnings are not shown for UTC or for a fixed time window
    Given the schedule "30 2 * * *"
    When the operator describes it with <options>
    Then no "DST transition" warning is shown

    Examples:
      | options                                                           |
      | --tz UTC                                                          |
      | --tz America/New_York --between 2027-03-13T00:00 2027-03-15T00:00 |
