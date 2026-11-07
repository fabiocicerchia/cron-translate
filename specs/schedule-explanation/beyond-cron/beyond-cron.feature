@domain:schedule-explanation @area:beyond-cron @from:cron-translate/cron-translate
Feature: Explaining intervals cron cannot express
  Tells operators when a requested interval can't be written exactly in cron, and what to use instead.

  @id:schedule-explanation.beyond-cron.001 @rule:schedule.beyond-cron.inexact-interval-runs-with-warning @verified @source:cron_translate.py#_minute_interval @test:tests/test_cron_translate.py#test_cli_runs_an_inexact_phrase_and_says_so @test:tests/test_cron_translate.py#test_phrase_uneven_minute_step_is_translated_but_flagged @test:tests/test_cron_translate.py#test_phrase_day_step_flags_the_month_boundary
  Scenario Outline: An interval cron can only approximate runs, with a warning that explains the uneven gap
    Given the phrase "<phrase>"
    When the operator describes the phrase
    Then the output shows the cron expression "<cron>" with its description
    And a line starting with "⚠" contains "<warning>"
    And the next runs of "<cron>" are listed
    And the exit status is 0

    Examples:
      | phrase          | cron        | warning                                                                             |
      | every 7 minutes | */7 * * * * | restarts at the top of every hour, so the gap across :00 is 4 minutes rather than 7 |
      | every 5 hours   | 0 */5 * * * | restarts at midnight, so the gap across 00:00 is 4 hours rather than 5              |
      | every 3 days    | 0 0 */3 * * | restarts on the 1st of every month                                                  |
      | every 5 months  | 0 0 1 */5 * | the gap across the year boundary is 2 months rather than 5                          |

  @id:schedule-explanation.beyond-cron.002 @rule:schedule.beyond-cron.inexpressible-refused-with-alternative @verified @source:cron_translate.py#_beyond_cron @test:tests/test_cron_translate.py#test_cli_reports_an_inexpressible_phrase @test:tests/test_cron_translate.py#test_phrase_every_two_weeks_is_refused_with_a_reason @test:tests/test_cron_translate.py#test_phrase_last_friday_offers_the_quartz_form @test:tests/test_cron_translate.py#test_phrase_nth_weekday_offers_the_hash_form @test:tests/test_cron_translate.py#test_phrase_last_day_of_month_offers_l_syntax @test:tests/test_cron_translate.py#test_phrase_interval_longer_than_an_hour_offers_crontab_lines @test:tests/test_cron_translate.py#test_intervals_beyond_a_field_have_no_cron_answer @test:tests/test_cron_translate.py#test_an_interval_that_does_not_tile_a_day_offers_no_crontab_lines @test:tests/test_cron_translate.py#test_interval_boundaries @questionable
  Scenario Outline: A schedule cron cannot express is refused with the reason and the closest alternative
    Given the phrase "<phrase>"
    When the operator describes the phrase
    Then no runs are listed
    And the error output starts with "cron-translate:" and contains "<explanation>"
    And the exit status is 64

    Examples:
      | phrase                    | explanation                                                         |
      | every 2 weeks             | cron has no week counter                                            |
      | every 2 weeks             | OnUnitActiveSec=2w                                                  |
      | every 90 minutes          | Closest: 0 0,3,6,9,12,15,18,21 * * *; 30 1,4,7,10,13,16,19,22 * * * |
      | every 36 hours            | OnUnitActiveSec=36h                                                 |
      | every 40 days             | OnUnitActiveSec=40d                                                 |
      | every 18 months           | OnUnitActiveSec=18months                                            |
      | every 2880 minutes        | none of its fields can count 2880 minutes                           |
      | last friday of the month  | 0 0 0 ? * 6L *                                                      |
      | third friday of the month | 0 0 0 ? * 6#3 *                                                     |
      | last day of the month     | 0 0 0 L * ? *                                                       |
      | every 0 minutes           | an interval of zero is not a schedule                               |

  @id:schedule-explanation.beyond-cron.003 @rule:schedule.beyond-cron.whole-unit-intervals-exact @verified @source:cron_translate.py#_interval_translation @test:tests/test_cron_translate.py#test_interval_boundaries @test:tests/test_cron_translate.py#test_phrase_even_steps_stay_exact
  Scenario Outline: Intervals that fit a cron field evenly are translated without a warning
    Given the phrase "<phrase>"
    When the operator describes the phrase
    Then the output shows the cron expression "<cron>"
    And no ⚠ warning line is shown

    Examples:
      | phrase           | cron         |
      | every 20 minutes | */20 * * * * |
      | every 1 day      | 0 0 * * *    |
      | every 24 hours   | 0 0 * * *    |
      | every 1 week     | 0 0 * * 0    |
      | every 1 month    | 0 0 1 * *    |
      | every 6 months   | 0 0 1 */6 *  |
      | every 12 months  | 0 0 1 1 *    |

  @id:schedule-explanation.beyond-cron.004 @rule:schedule.beyond-cron.hour-multiples-in-minutes-refused @inferred @source:cron_translate.py#_minute_interval @questionable
  Scenario Outline: A minute interval that is a whole number of hours is refused although cron can express it
    Given the phrase "<phrase>"
    When the operator describes the phrase
    Then no runs are listed
    And the error output contains "cron's minute field stops at 59" and "Closest: <closest>"
    And the exit status is 64

    Examples:
      | phrase            | closest                                                               |
      | every 60 minutes  | 0 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23 * * * |
      | every 120 minutes | 0 0,2,4,6,8,10,12,14,16,18,20,22 * * *                                |
