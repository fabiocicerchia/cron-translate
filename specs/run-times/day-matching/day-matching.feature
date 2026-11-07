@domain:run-times @area:day-matching @from:cron-translate/cron-translate
Feature: Combining day-of-month and weekday
  Makes listed runs match what the crontab on the machine will actually do when both day fields are set.

  @id:run-times.day-matching.005 @rule:runs.day-matching.star-field-requires-both @verified @source:cron_translate.py#_schedule @test:tests/test_cron_translate.py#test_the_cli_reads_the_day_fields_the_way_the_crontab_will @test:tests/test_cron_translate.py#test_a_day_rule_without_a_star_accepts_either_field
  Scenario Outline: Both day fields must match when either is written with a star; otherwise either is enough
    Given the schedule "<expression>"
    When the operator lists its runs between <start> and <end>
    Then runs on <listed> appear
    And runs on <not_listed> do not appear

    Examples:
      | expression     | start            | end              | listed                       | not_listed                |
      | 0 9 */10 * 1-5 | 2026-09-12T00:00 | 2026-11-30T00:00 | 2026-09-21 (4 runs in total) | 2026-11-01 and 2026-09-14 |
      | 0 9 1 * 1      | 2026-09-12T00:00 | 2026-09-30T00:00 | 2026-09-14 and 2026-09-21    | none                      |
