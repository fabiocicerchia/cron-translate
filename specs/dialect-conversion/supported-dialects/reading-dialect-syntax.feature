@domain:dialect-conversion @area:supported-dialects @from:cron-translate/cron-dialects
Feature: Reading schedules in each dialect's syntax
  Lets an operator name a dialect the way they know it and paste a schedule in its native form, and refuses input that dialect would not accept.

  @id:dialect-conversion.supported-dialects.001 @rule:dialect-conversion.dialects.aliases-accepted @verified @source:cron_dialects.py#resolve @test:tests/test_dialects.py#test_aliases_resolve
  Scenario Outline: Common names for a dialect are accepted
    Given the supported dialects are vixie, k8s, eventbridge, quartz and systemd
    When the operator names the dialect as <alias>
    Then the schedule is read as <dialect>

    Examples:
      | alias      | dialect     |
      | cron       | vixie       |
      | crontab    | vixie       |
      | unix       | vixie       |
      | kubernetes | k8s         |
      | cronjob    | k8s         |
      | aws        | eventbridge |
      | OnCalendar | systemd     |
      | timer      | systemd     |

  @id:dialect-conversion.supported-dialects.002 @rule:dialect-conversion.dialects.unknown-dialect-refused @verified @source:cron_dialects.py#resolve @test:tests/test_dialects.py#test_unknown_dialect_is_rejected
  Scenario: An unknown dialect is refused with the list of known ones
    Given no dialect is called cronicle
    When the operator converts 0 9 * * 1-5 from vixie to cronicle
    Then the conversion is refused
    And the message reads unknown dialect 'cronicle'; known dialects are eventbridge, k8s, quartz, systemd, vixie

  @id:dialect-conversion.supported-dialects.003 @rule:dialect-conversion.dialects.native-shorthands-accepted @verified @source:cron_dialects.py#_expand_macro @test:tests/test_dialects.py#test_macro_expands @test:tests/test_dialects.py#test_systemd_shorthand @test:tests/test_dialects.py#test_eventbridge_cron_wrapper_is_accepted @test:tests/test_dialects.py#test_quartz_year_field_is_optional @test:tests/test_dialects.py#test_systemd_time_field_is_not_mistaken_for_a_timezone
  Scenario Outline: Each dialect's shorthand and wrapper forms are accepted as input
    Given a schedule written as <expression> in <source>
    When the operator converts it from <source> to <target>
    Then the converted expression is <converted>

    Examples:
      | source      | expression          | target | converted       |
      | vixie       | @daily              | quartz | 0 0 0 * * ? *   |
      | systemd     | daily               | vixie  | 0 0 * * *       |
      | eventbridge | cron(0 9 ? * 2-6 *) | vixie  | 0 9 * * 1-5     |
      | quartz      | 0 0 9 ? * 2-6       | vixie  | 0 9 * * 1-5     |
      | systemd     | *-*-* *:0/15:00     | vixie  | 0-59/15 * * * * |

  @id:dialect-conversion.supported-dialects.004 @rule:dialect-conversion.dialects.invalid-source-refused @verified @source:cron_dialects.py#parse_field @test:tests/test_dialects.py#test_invalid_source_expressions_are_rejected
  Scenario Outline: A schedule the source dialect would not accept is refused
    Given <expression> breaks a rule of <source>
    When the operator converts it from <source> to vixie
    Then the conversion is refused
    And the message reads <message>

    Examples:
      | source      | expression      | message                                                                                                     |
      | vixie       | 0 9 * * 1-5 *   | vixie cron expects 5 fields, got 6: '0 9 * * 1-5 *'                                                         |
      | vixie       | @reboot         | @reboot is not a calendar schedule: it has no next run and no equivalent in any dialect                     |
      | k8s         | 0 0 * * 7       | 7 is outside the day-of-week range 0-6                                                                      |
      | eventbridge | 0 9 * * * *     | EventBridge requires '?' in exactly one of day-of-month and day-of-week; this expression gives both a value |
      | eventbridge | 0 9 ? * 2-6/2 * | the day-of-week field of this dialect does not accept a step ('2-6/2')                                      |
      | quartz      | 0 0 9 ? * ? *   | Quartz needs a value in one of day-of-month and day-of-week; both are '?'                                   |
      | quartz      | 0 9 ? * 2-6     | Quartz expects 6 or 7 fields, got 5: '0 9 ? * 2-6'                                                          |
      | systemd     | nonsense        | 'nonsense' is not a systemd date: expected Y-M-D or M-D                                                     |
