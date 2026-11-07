@domain:run-times @area:day-matching @from:cron-translate/cron-dialects
Feature: Which days a dialect schedule fires on
  Shows an operator the real fire dates of special-day and two-day-field schedules, so a conversion can be checked against the calendar.

  Background:
    Given the clock reads 2026-09-11 10:00 UTC

  @id:run-times.day-matching.001 @rule:run-times.day-matching.special-days @verified @source:cron_dialects.py#_dom_matches @test:tests/test_dialects.py#test_last_day_of_month @test:tests/test_dialects.py#test_days_before_the_last_day @test:tests/test_dialects.py#test_nth_weekday_of_month @test:tests/test_dialects.py#test_last_weekday_of_month @test:tests/test_dialects.py#test_last_weekday_of_the_month @test:tests/test_dialects.py#test_nearest_weekday_never_leaves_the_month
  Scenario Outline: Last-day, nearest-weekday and nth-weekday schedules fire on the right calendar days
    Given a Quartz schedule <expression> that fires at noon on <meaning>
    When the operator converts it from quartz to quartz
    Then the first proof runs fall on <dates>

    Examples:
      | expression       | meaning                                                | dates                              |
      | 0 0 12 L * ? *   | the last day of the month                              | 2026-09-30, 2026-10-31, 2026-11-30 |
      | 0 0 12 L-3 * ? * | three days before the last day                         | 2026-09-27, 2026-10-28, 2026-11-27 |
      | 0 0 12 ? * 6#3 * | the third Friday                                       | 2026-09-18, 2026-10-16, 2026-11-20 |
      | 0 0 12 ? * 6L *  | the last Friday                                        | 2026-09-25, 2026-10-30, 2026-11-27 |
      | 0 0 12 LW * ? *  | the last weekday                                       | 2026-09-30, 2026-10-30             |
      | 0 0 12 1W * ? *  | the weekday nearest the 1st, without leaving the month | 2026-10-01, 2026-11-02, 2026-12-01 |

  @id:run-times.day-matching.002 @rule:run-times.day-matching.systemd-both-cron-either @verified @source:cron_dialects.py#_day_matches @test:tests/test_dialects.py#test_systemd_requires_both_weekday_and_date @test:tests/test_dialects.py#test_cron_accepts_either_weekday_or_date
  Scenario Outline: systemd needs both the date and the weekday to match, cron needs either
    Given a schedule <expression> in <source> naming the 1st of the month and Monday
    When the operator converts it from <source> to <source>
    Then the first proof runs fall on <dates>

    Examples:
      | source  | expression          | dates                              |
      | systemd | Mon *-*-01 09:00:00 | 2027-02-01, 2027-03-01             |
      | vixie   | 0 9 1 * 1           | 2026-09-14, 2026-09-21, 2026-09-28 |

  @id:run-times.day-matching.003 @rule:run-times.day-matching.cron-star-rule @verified @source:cron_dialects.py#cron_day_match @test:tests/test_dialects.py#test_star_step_day_of_month_requires_both_fields @test:tests/test_dialects.py#test_full_week_day_of_week_against_a_star_step @test:tests/test_dialects.py#test_full_week_day_of_week_without_a_star_matches_every_day @test:tests/test_dialects.py#test_whole_week_range_is_still_a_restricted_field
  Scenario Outline: In crontab a star in either day field makes both fields apply, and a full-week range still counts as a restriction
    Given a vixie schedule <expression>
    When the operator converts it from vixie to vixie
    Then the first proof runs fall on <dates>

    Examples:
      | expression     | dates                                          |
      | 0 9 */10 * 1-5 | 2026-09-21, 2026-10-01, 2026-10-21, 2026-11-11 |
      | 0 9 */10 * 1-7 | 2026-09-21, 2026-10-01, 2026-10-11, 2026-10-21 |
      | 0 9 1 * 0-7    | 2026-09-12, 2026-09-13, 2026-09-14             |
      | 0 9 1 * *      | 2026-10-01, 2026-11-01                         |

  @id:run-times.day-matching.004 @rule:run-times.day-matching.sparse-schedules @verified @source:cron_dialects.py#next_runs @test:tests/test_dialects.py#test_year_field_limits_the_walk @test:tests/test_dialects.py#test_horizon_reaches_far_enough_for_a_sparse_schedule
  Scenario Outline: Rare and year-limited schedules list every run they have, and no more
    Given a Quartz schedule <expression>
    When the operator converts it from quartz to quartz asking for <count> runs
    Then the proof runs are <runs>

    Examples:
      | expression        | count | runs                               |
      | 0 0 12 1 1 ? 2028 | 5     | 2028-01-01 12:00 only              |
      | 0 0 0 29 2 ? *    | 3     | 2028-02-29, 2032-02-29, 2036-02-29 |
