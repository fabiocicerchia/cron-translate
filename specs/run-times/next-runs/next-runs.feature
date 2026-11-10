@domain:run-times @area:next-runs @from:cron-translate/cron-translate
Feature: Listing upcoming runs
  Shows operators when a schedule will next fire, on the clock of the zone they choose.

  @id:run-times.next-runs.001 @rule:runs.next.upcoming-runs-with-countdown @verified @source:cron_translate.py#_render_text @test:tests/test_cron_translate.py#test_cli_happy_path
  Scenario Outline: Upcoming runs are listed in the chosen zone, each with how far away it is
    Given the schedule "0 3 * * *"
    When the operator describes it with <options>
    Then the heading reads "Next <count> runs (<zone>):"
    And <count> run lines follow, each showing date, HH:MM time and zone abbreviation
    And each run line ends with a countdown in days, such as "(in 2d)", when the run is a day or more away, otherwise in hours, such as "(in 3.5h)"

    Examples:
      | options                   | count | zone        |
      | no options                | 3     | UTC         |
      | --next 1                  | 1     | UTC         |
      | --next 5 --tz Europe/Rome | 5     | Europe/Rome |
