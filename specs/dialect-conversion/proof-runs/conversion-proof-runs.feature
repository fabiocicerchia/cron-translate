@domain:dialect-conversion @area:proof-runs @from:cron-translate/cron-dialects
Feature: Proving a conversion with side-by-side runs
  Gives an operator evidence that the converted schedule fires at the same moments as the original.

  @id:dialect-conversion.proof-runs.001 @rule:dialect-conversion.proof-runs.both-sides-agree @verified @source:cron_dialects.py#convert @test:tests/test_dialects.py#test_every_pair_agrees_on_the_next_runs
  Scenario Outline: The converted schedule, read back by the target's own rules, fires at the same times as the original
    Given a schedule <expression> in <source>
    When the operator converts it from <source> to <target>
    Then the next 5 runs of the original and of the converted expression are identical

    Examples:
      | source  | expression              | target      |
      | vixie   | 0 9 * * 1-5             | systemd     |
      | systemd | Mon..Fri *-*-* 09:00:00 | eventbridge |
      | quartz  | 0 0 9 ? * 2-6 *         | k8s         |
