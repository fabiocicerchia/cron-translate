@domain:dialect-conversion @area:proof-runs @from:cron-translate/cron-translate
Feature: Proving a conversion with side-by-side runs
  Shows operators both schedules' upcoming runs on one clock so they can trust a conversion before deploying it.

  @id:dialect-conversion.proof-runs.002 @rule:convert.proof.side-by-side-runs @verified @source:cron_translate.py#_render_conversion @test:tests/test_cron_translate.py#test_convert_prints_both_expressions_and_both_run_lists @test:tests/test_cron_translate.py#test_convert_describes_the_schedule_once
  Scenario: A conversion shows both expressions, one description and both run lists on the same clock
    Given the quartz schedule "0 0 12 ? * MON-FRI *"
    When the operator converts it to eventbridge
    Then the first two lines show each dialect's name with its expression, the target being "0 12 ? * 2-6 *"
    And one "→" description line follows
    And the heading reads "Next 3 runs (UTC), both dialects on the same clock:"
    And each row shows the source run and the target run to the second
    And each caveat appears on its own ⚠ line
    And the exit status is 0

  @id:dialect-conversion.proof-runs.003 @rule:convert.proof.disagreement-reported @inferred @source:cron_translate.py#_convert_main
  Scenario: When the converted schedule's runs differ from the original's, the conversion is flagged and fails
    Given a conversion whose target runs differ from its source runs
    When the operator converts the schedule
    Then a line reads "⚠ the two expressions do not agree — this is a bug in cron-translate, please report it"
    And a missing run in the shorter column shows "—"
    And in JSON output "agree" is false
    And the exit status is 65
