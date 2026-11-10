@domain:command-line @area:errors @from:cron-translate/cron-translate
Feature: Reporting errors and exit codes
  Tells operators and scripts clearly why a command was refused, with a distinct exit status.

  @id:command-line.errors.001 @rule:cli.errors.invalid-expression @verified @source:cron_translate.py#_resolve_expression @test:tests/test_cron_translate.py#test_invalid_expression_diagnostic_goes_to_stderr @test:tests/test_cron_translate.py#test_invalid_expression_exit_code @test:tests/test_cron_translate.py#test_phrase_unrecognized_returns_none
  Scenario Outline: Input that is neither cron nor a recognised phrase is refused as invalid
    Given the input "<input>"
    When the operator describes the input
    Then the error output reads "cron-translate: invalid cron expression: '<input>'"
    And nothing is printed on standard output
    And the exit status is 64

    Examples:
      | input                  |
      | total nonsense         |
      | do the thing sometimes |
      | every day at 25pm      |


  @id:command-line.errors.003 @rule:cli.errors.impossible-conversion @verified @source:cron_translate.py#_report_impossible @test:tests/test_cron_translate.py#test_convert_offers_the_closest_expression_on_stderr @test:tests/test_cron_translate.py#test_convert_refuses_an_impossible_pair
  Scenario: A conversion the target cannot express is refused, with the closest non-equivalent expression
    Given the quartz schedule "30 0 12 ? * MON-FRI *"
    When the operator converts it to vixie
    Then the error output contains "cannot convert to vixie:" followed by the reason
    And the error output contains "closest vixie expression, which is NOT equivalent: 0 12 * * 1-5"
    And no runs are listed
    And the exit status is 65

  @id:command-line.errors.004 @rule:cli.errors.bad-zone-or-time-crashes @inferred @source:cron_translate.py#_describe_main @questionable
  Scenario Outline: An unknown time zone or unreadable window time ends in a traceback instead of a clear message
    Given the schedule "0 3 * * *"
    When the operator <command>
    Then a Python traceback is printed instead of a one-line message
    And no JSON error object is printed, even with --json
    And the exit status is 1, not 64

    Examples:
      | command                                                  |
      | describes it with --tz Mars/Olympus                      |
      | lists its runs between "yesterday" and "tomorrow"        |
      | converts it from vixie to systemd with --tz Mars/Olympus |
