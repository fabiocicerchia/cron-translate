@domain:dialect-conversion @area:convert @from:cron-translate/cron-dialects
Feature: Converting a schedule between cron dialects
  Lets an operator move a schedule between crontab, Kubernetes, EventBridge, Quartz and systemd without changing which days and times it fires.

  @id:dialect-conversion.convert.001 @rule:dialect-conversion.convert.same-schedule-in-every-dialect @verified @source:cron_dialects.py#convert @test:tests/test_dialects.py#test_every_pair_converts_to_the_canonical_form
  Scenario Outline: A schedule every dialect can express converts to that dialect's own spelling
    Given a schedule that fires on weekdays at 09:00 written as <expression> in <source>
    When the operator converts it from <source> to <target>
    Then the converted expression is <converted>

    Examples:
      | source      | expression              | target      | converted               |
      | vixie       | 0 9 * * 1-5             | eventbridge | 0 9 ? * 2-6 *           |
      | vixie       | 0 9 * * 1-5             | quartz      | 0 0 9 ? * 2-6 *         |
      | vixie       | 0 9 * * 1-5             | systemd     | Mon..Fri *-*-* 09:00:00 |
      | quartz      | 0 0 9 ? * 2-6 *         | k8s         | 0 9 * * 1-5             |
      | systemd     | Mon..Fri *-*-* 09:00:00 | eventbridge | 0 9 ? * 2-6 *           |
      | eventbridge | 0 9 ? * 2-6 *           | vixie       | 0 9 * * 1-5             |

  @id:dialect-conversion.convert.002 @rule:dialect-conversion.convert.weekday-numbering-preserved @verified @source:cron_dialects.py#_normalise_dow @test:tests/test_dialects.py#test_weekday_numbering_survives_the_round_trip @test:tests/test_dialects.py#test_sunday_seven_is_sunday_zero
  Scenario Outline: Weekday numbers are renumbered so the same day is kept
    Given <source> numbers Sunday as <sunday_in_source> and <target> numbers it as <sunday_in_target>
    When the operator converts <expression> from <source> to <target>
    Then the converted expression is <converted>
    And it fires on <weekday>

    Examples:
      | source | expression | target | sunday_in_source | sunday_in_target | converted     | weekday |
      | vixie  | 0 9 * * 1  | quartz | 0 or 7           | 1                | 0 0 9 ? * 2 * | Monday  |
      | vixie  | 0 0 * * 7  | k8s    | 0 or 7           | 0                | 0 0 * * 0     | Sunday  |

  @id:dialect-conversion.convert.003 @rule:dialect-conversion.convert.ranges-and-steps-rewritten @verified @source:cron_dialects.py#_render_term @test:tests/test_dialects.py#test_wrapping_weekday_range_keeps_its_step @test:tests/test_dialects.py#test_wrapping_weekday_range_without_a_step @test:tests/test_dialects.py#test_stepped_weekday_is_not_dropped_by_systemd @test:tests/test_dialects.py#test_open_ended_weekday_step_keeps_its_step_in_systemd @test:tests/test_dialects.py#test_open_ended_step_renders_as_a_range_for_five_field_dialects @test:tests/test_dialects.py#test_systemd_repetition_round_trips @test:tests/test_dialects.py#test_whole_week_range_covers_every_day
  Scenario Outline: Ranges and steps are rewritten in a form the target reads the same way
    Given a schedule written as <expression> in <source>
    When the operator converts it from <source> to <target>
    Then the converted expression is <converted>

    Examples:
      | source  | expression       | target      | converted                      |
      | vixie   | 0 9 * * 5-1/2    | quartz      | 0 0 9 ? * 6,1 *                |
      | vixie   | 0 9 * * 5-1/2    | systemd     | Fri,Sun *-*-* 09:00:00         |
      | vixie   | 0 0 * * 5-1      | eventbridge | 0 0 ? * 6,7,1,2 *              |
      | vixie   | 0 0 * * */2      | systemd     | Sun,Tue,Thu,Sat *-*-* 00:00:00 |
      | quartz  | 0 0 0 ? * 2/2    | systemd     | Mon,Wed,Fri *-*-* 00:00:00     |
      | quartz  | 0 0 0 5/10 * ? * | vixie       | 0 0 5-31/10 * *                |
      | systemd | *-*-* 00/6:00:00 | quartz      | 0 0 0-23/6 * * ? *             |
      | vixie   | 0 0 * * 0-7      | quartz      | 0 0 0 ? * 1-7 *                |

  @id:dialect-conversion.convert.004 @rule:dialect-conversion.convert.last-day-as-systemd-tilde @verified @source:cron_dialects.py#_systemd_term @test:tests/test_dialects.py#test_systemd_last_day_uses_tilde @questionable
  Scenario: The last day of the month is written with systemd's tilde
    Given a Quartz schedule 0 0 12 L * ? * that fires at noon on the last day of each month
    When the operator converts it from quartz to systemd
    Then the converted expression is *-*-~01 12:00:00
