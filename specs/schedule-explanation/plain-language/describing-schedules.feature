@domain:schedule-explanation @area:plain-language @from:cron-translate/cron-translate
Feature: Describing a cron schedule in plain language
  Lets operators read what a cron expression means before trusting it to run a job.

  @id:schedule-explanation.plain-language.001 @rule:schedule.describe.plain-english-sentence @verified @source:cron_translate.py#describe @test:tests/test_cron_translate.py#test_describe_simple_time @test:tests/test_cron_translate.py#test_describe_weekdays
  Scenario Outline: A cron expression is shown with its plain-English meaning in 24-hour time
    Given the cron expression "<expression>"
    When the operator describes the expression
    Then the output starts with "<expression>"
    And the next line starts with "→" and contains "<description>"
    And the next runs follow the description

    Examples:
      | expression        | description      |
      | 0 3 * * *         | At 03:00         |
      | */15 9-17 * * 1-5 | Every 15 minutes |

  @id:schedule-explanation.plain-language.002 @rule:schedule.describe.trailing-seconds-field @verified @source:cron_translate.py#_seconds_first @test:tests/test_cron_translate.py#test_croniter_seconds_field_is_moved_to_the_front_for_the_description @test:tests/test_cron_translate.py#test_cli_describes_a_six_field_expression_correctly
  Scenario Outline: A sixth field after the weekday is read as seconds, and a seventh as the year
    Given the six- or seven-field expression "<expression>"
    When the operator describes the expression
    Then the description reads "<description>"

    Examples:
      | expression        | description                            |
      | 0 12 * * 1 0      | At 12:00, only on Monday               |
      | 0 12 * * 1 30     | At 12:00:30, only on Monday            |
      | 0 12 * * 1 0 2027 | At 12:00, only on Monday, only in 2027 |

  @id:schedule-explanation.plain-language.003 @rule:schedule.describe.falls-back-to-expression @inferred @source:cron_translate.py#describe
  Scenario: When no description can be worded, the expression itself is shown and the runs still list
    Given an expression the scheduler accepts but the describer cannot word
    When the operator describes the expression
    Then the "→" line repeats the expression unchanged
    And the next runs are still listed
    And the exit status is 0
