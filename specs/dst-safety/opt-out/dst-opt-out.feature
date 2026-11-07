@domain:dst-safety @area:opt-out @from:cron-translate/cron-translate
Feature: Turning off DST checks
  Lets operators silence DST flags and warnings when they don't need them.

  @id:dst-safety.opt-out.001 @rule:dst.opt-out.no-dst-check @verified @source:cron_translate.py#_describe_main @test:tests/test_cron_translate.py#test_no_dst_check_suppresses_the_run_flags
  Scenario Outline: With DST checks turned off, no run is flagged and no transition is warned about
    Given the schedule "30 2 * * *" in America/New_York
    When the operator <command> with --no-dst-check
    Then no ⚠ DST flag appears on any run line
    And no "DST transition" warning is shown
    And in JSON output every run_dst entry is null

    Examples:
      | command                                                      |
      | lists its runs between 2027-03-13T00:00 and 2027-03-15T00:00 |
      | describes it                                                 |
