@domain:dialect-conversion @area:caveats-and-limits @from:cron-translate/cron-dialects
Feature: Refusing or qualifying conversions that would change a schedule's meaning
  Keeps an operator from deploying a converted schedule that silently fires at different times: it refuses what the target cannot say and flags nuances that shift.

  @id:dialect-conversion.caveats-and-limits.001 @rule:dialect-conversion.caveats.missing-feature-refused @verified @source:cron_dialects.py#_reject_specials @test:tests/test_dialects.py#test_impossible_conversions_refuse_and_say_why
  Scenario Outline: A schedule using a feature the target lacks is refused with the reason
    Given a schedule written as <expression> in <source>
    When the operator converts it from <source> to <target>
    Then no converted expression is given
    And the reason reads <reason>

    Examples:
      | source      | expression         | target      | reason                                                                                           |
      | quartz      | 30 0 9 ? * 2-6 *   | vixie       | vixie cron has no seconds field, and this schedule fires at second 30 rather than only at :00    |
      | quartz      | 0 0 9 ? * 6#3 *    | k8s         | Kubernetes CronJob has no `L`, `W` or `#`: it cannot express 6#3                                 |
      | quartz      | 0 0 9 ? * 6#3 *    | systemd     | systemd OnCalendar has no nth-weekday or last-weekday syntax: it cannot express 6#3              |
      | quartz      | 0 0 9 15W * ? *    | systemd     | systemd OnCalendar has no nearest-weekday syntax: it cannot express 15W                          |
      | quartz      | 0 0 9 L-3 * ? *    | eventbridge | EventBridge documents `L` only as the last day of the month; `L-n` is Quartz                     |
      | quartz      | 0 0 9 ? * 2-6 2027 | vixie       | vixie cron has no year field, so it cannot limit a schedule to 2027                              |
      | eventbridge | 0 9 ? * 2-6 2150   | quartz      | Quartz years stop at 2099; this schedule reaches 2150                                            |
      | quartz      | 0 0 9 ? * 2-6/2 *  | eventbridge | EventBridge's day-of-week field does not accept `/`; its wildcards are , - * ? L #               |
      | quartz      | 0 0 9 ? * 6#3,2 *  | eventbridge | EventBridge allows only one expression in day-of-week when `#` is used: 6#3,2 is read as several |


  @id:dialect-conversion.caveats-and-limits.003 @rule:dialect-conversion.caveats.day-rule-mismatch-refused @verified @source:cron_dialects.py#_reject_and_semantics @test:tests/test_dialects.py#test_impossible_conversions_refuse_and_say_why @test:tests/test_dialects.py#test_without_a_star_systemd_still_refuses
  Scenario Outline: A schedule whose day-of-month and weekday combine differently in the target is refused
    Given a schedule written as <expression> in <source> that restricts both the date and the weekday
    When the operator converts it from <source> to <target>
    Then no converted expression is given
    And the reason starts with <reason>

    Examples:
      | source  | expression               | target      | reason                                                                                               |
      | vixie   | 0 9 1 * 1-5              | eventbridge | EventBridge requires `?` in exactly one of day-of-month and day-of-week, so it cannot restrict both. |
      | vixie   | 0 9 1 * 1-5              | quartz      | Quartz requires `?` in exactly one of day-of-month and day-of-week, so it cannot restrict both.      |
      | vixie   | 0 9 1 * 1-5              | systemd     | cron fires when day-of-month OR day-of-week matches; `OnCalendar=` fires only when both match.       |
      | systemd | Mon..Fri *-*-01 09:00:00 | vixie       | systemd ANDs the weekday against the date, and vixie cron ORs them                                   |
      | systemd | Mon..Fri *-*-01 09:00:00 | quartz      | systemd ANDs the weekday against the date, and Quartz ORs them                                       |

  @id:dialect-conversion.caveats-and-limits.004 @rule:dialect-conversion.caveats.starred-day-field-reaches-systemd @verified @source:cron_dialects.py#cron_day_match @test:tests/test_dialects.py#test_a_starred_day_field_makes_systemd_reachable @questionable
  Scenario: A crontab entry whose date field uses a star converts to systemd, because both already require both days
    Given a vixie schedule 0 9 */10 * 1-5 whose day-of-month is written with a star
    When the operator converts it from vixie to systemd
    Then the converted expression is Mon..Fri *-*-01/10 09:00:00

  @id:dialect-conversion.caveats-and-limits.005 @rule:dialect-conversion.caveats.day-field-notes @verified @source:cron_dialects.py#_day_caveats @test:tests/test_dialects.py#test_question_mark_conversion_carries_a_caveat
  Scenario Outline: A conversion that rewrites the day fields says how
    Given a schedule written as <expression> in <source>
    When the operator converts it from <source> to <target>
    Then the conversion carries the caveat <caveat>

    Examples:
      | source      | expression              | target  | caveat                                                                                                                                                                                              |
      | eventbridge | 0 9 ? * 2-6 *           | vixie   | `?` (no specific value) has no meaning in a 5-field crontab and is written `*`; the effect is the same here because the other day field carries the restriction.                                    |
      | vixie       | @daily                  | quartz  | `*` in both day fields is not legal in this dialect: day-of-week is written `?`, which means the same thing.                                                                                        |
      | quartz      | 0 0 9 ? * 2-6 *         | systemd | `?` becomes `*`: systemd has no 'no specific value', it simply ANDs the two.                                                                                                                        |
      | systemd     | Mon..Fri *-*-* 09:00:00 | vixie   | cron ORs day-of-month against day-of-week only when both are restricted and neither is written with a star; systemd always ANDs them. This schedule falls on the side where the two readings agree. |

  @id:dialect-conversion.caveats-and-limits.006 @rule:dialect-conversion.caveats.time-zone-placement @verified @source:cron_dialects.py#render_k8s @test:tests/test_dialects.py#test_timezone_survives_from_systemd_as_a_caveat
  Scenario Outline: A conversion says where the target keeps the time zone
    Given a systemd schedule <expression>
    When the operator converts it from systemd to <target>
    Then the converted expression has no time zone in it
    And the conversion carries a caveat containing <caveat>

    Examples:
      | expression                          | target      | caveat                                                                                                      |
      | Mon..Fri *-*-* 09:00:00 Europe/Rome | k8s         | set `spec.timeZone: Europe/Rome` on the CronJob (Kubernetes 1.27+).                                         |
      | Mon..Fri *-*-* 09:00:00 Europe/Rome | vixie       | put `CRON_TZ=Europe/Rome` on a line above the entry                                                         |
      | Mon..Fri *-*-* 09:00:00 Europe/Rome | eventbridge | EventBridge rules fire in UTC; only EventBridge Scheduler takes a ScheduleExpressionTimezone (Europe/Rome). |
      | Mon..Fri *-*-* 09:00:00 Europe/Rome | quartz      | call `.inTimeZone(TimeZone.getTimeZone("Europe/Rome"))` on the CronScheduleBuilder.                         |
      | Mon..Fri *-*-* 09:00:00             | k8s         | with no `spec.timeZone`, a CronJob runs in the kube-controller-manager's zone                               |
