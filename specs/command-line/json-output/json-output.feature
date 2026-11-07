@domain:command-line @area:json-output @from:cron-translate/cron-translate
Feature: JSON output for scripts
  Gives automation the same results as structured JSON so scripts can read them reliably.

  @id:command-line.json-output.001 @rule:cli.json.describe-report @verified @source:cron_translate.py#_render_json @test:tests/test_cron_translate.py#test_cli_json_output @test:tests/test_cron_translate.py#test_json_carries_the_per_run_dst_notes
  Scenario: A described schedule is reported as one JSON object
    Given the schedule "0 3 * * *"
    When the operator describes it with --next 2 --json
    Then stdout is a single JSON object
    And "expression" is "0 3 * * *" and "tz" is "UTC"
    And "runs" holds 2 ISO 8601 timestamps with offset, and "run_dst" holds one entry per run, null when unaffected
    And "dst_warnings" is an empty list and "note" is null
    And "description" holds the plain-English description

  @id:command-line.json-output.002 @rule:cli.json.convert-report @verified @source:cron_translate.py#_render_conversion_json @test:tests/test_cron_translate.py#test_convert_json
  Scenario: A conversion is reported as one JSON object with both run lists and whether they agree
    Given the vixie schedule "0 9 * * 1-5"
    When the operator converts it to systemd with --json
    Then "target" is "Mon..Fri *-*-* 09:00:00"
    And "source_runs" and "target_runs" list the same timestamps and "agree" is true
    And the object also carries "from", "to", "source", "description", "tz", "run_dst" and "caveats"

  @id:command-line.json-output.003 @rule:cli.json.errors-as-json @verified @source:cron_translate.py#_fail @test:tests/test_cron_translate.py#test_cli_json_invalid_expression @test:tests/test_cron_translate.py#test_convert_json_impossible
  Scenario Outline: In JSON mode a refusal is printed as a JSON error object on standard output
    Given <situation>
    When the operator runs the command with --json
    Then stdout is the JSON object <body>
    And the exit status is <status>

    Examples:
      | situation                                               | body                                                                       | status |
      | the expression "not a cron"                             | {"error": "invalid cron expression: 'not a cron'"}                         | 64     |
      | the phrase "every 2 weeks"                              | {"error": "<the explanation>"}                                             | 64     |
      | a conversion to an unknown dialect                      | {"error": "<the message>"}                                                 | 64     |
      | a quartz schedule "0 0 12 ? * 6#3 *" converted to vixie | {"error": "<reason>", "closest": <expression or null>, "impossible": true} | 65     |
