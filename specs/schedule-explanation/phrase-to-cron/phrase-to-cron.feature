@domain:schedule-explanation @area:phrase-to-cron @from:cron-translate/cron-translate
Feature: Writing a schedule as an English phrase
  Lets operators type a schedule in English and get the cron expression and its runs.

  @id:schedule-explanation.phrase-to-cron.001 @rule:schedule.phrase.translates-to-cron @verified @source:cron_translate.py#translate_phrase @test:tests/test_cron_translate.py#test_phrase_weekday_at_time @test:tests/test_cron_translate.py#test_phrase_pm_and_minutes @test:tests/test_cron_translate.py#test_phrase_named_day @test:tests/test_cron_translate.py#test_phrase_interval @test:tests/test_cron_translate.py#test_cli_reverse_mode @test:tests/test_cron_translate.py#test_interval_boundaries @test:tests/test_cron_translate.py#test_phrase_even_steps_stay_exact
  Scenario Outline: A recognised English phrase becomes a cron expression and is described and run
    Given the phrase "<phrase>"
    When the operator describes the phrase
    Then the output shows the cron expression "<cron>" with its description
    And the next runs of "<cron>" are listed
    And no ⚠ warning line is shown
    And the exit status is 0

    Examples:
      | phrase                | cron         |
      | every weekday at 9am  | 0 9 * * 1-5  |
      | every day at 5:30pm   | 30 17 * * *  |
      | every monday at 9am   | 0 9 * * 1    |
      | every weekend at 10am | 0 10 * * 6,0 |
      | every day at 12am     | 0 0 * * *    |
      | every 15 minutes      | */15 * * * * |
      | every 2 hours         | 0 */2 * * *  |
      | every 20 minutes      | */20 * * * * |
      | every 1 day           | 0 0 * * *    |
      | every 24 hours        | 0 0 * * *    |
      | every 1 week          | 0 0 * * 0    |
      | every 1 month         | 0 0 1 * *    |
      | every 6 months        | 0 0 1 */6 *  |
      | every 12 months       | 0 0 1 1 *    |

  @id:schedule-explanation.phrase-to-cron.002 @rule:schedule.phrase.unrecognised-words-dropped @inferred @source:cron_translate.py#_weekday_field @questionable
  Scenario Outline: Words the translator does not understand are dropped without a warning
    Given the phrase "<phrase>"
    When the operator describes the phrase
    Then the schedule runs as "<cron>"
    And no warning says part of the phrase was ignored

    Examples:
      | phrase                         | cron      |
      | every monday and friday at 9am | 0 9 * * 1 |
      | every 2 hours at 9am           | 0 9 * * * |
      | repeat 5 times                 | 0 5 * * * |
