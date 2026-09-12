# Dialects

`cron-translate convert` reads one dialect, writes another, and refuses when
the target cannot say what the source said. This page is the reference for
what each dialect accepts and where the seams are.

```sh
cron-translate convert --from quartz --to eventbridge '0 0 12 ? * MON-FRI *'
```

Names are case-insensitive and take aliases: `cron`/`crontab`/`unix` for
`vixie`, `kubernetes`/`cronjob` for `k8s`, `aws` for `eventbridge`,
`oncalendar`/`timer` for `systemd`.

## vixie cron

Five fields, `minute hour day-of-month month day-of-week`.

| Field | Values | Accepts |
|---|---|---|
| minute | 0-59 | `,` `-` `*` `/` |
| hour | 0-23 | `,` `-` `*` `/` |
| day-of-month | 1-31 | `,` `-` `*` `/` |
| month | 1-12, `JAN`-`DEC` | `,` `-` `*` `/` |
| day-of-week | 0-7, `SUN`-`SAT` (0 and 7 are both Sunday) | `,` `-` `*` `/` |

`@yearly`, `@annually`, `@monthly`, `@weekly`, `@daily`, `@midnight` and
`@hourly` are expanded on the way in. `@reboot` is rejected: it is not a
calendar schedule, so it has no next run and no equivalent anywhere.

When both day fields are restricted, vixie fires when **either** matches. That
is the single most-misread rule in cron, and it is why `0 0 15-21 * 5` is not
"the third Friday".

The rule keys off the literal `*`, not off how many values a field matches. If
either day field is *written* with a star — `*/10` counts — vixie ANDs the two
instead:

| Expression | Reading |
|---|---|
| `0 9 1 * 1` | the 1st **or** any Monday |
| `0 9 */10 * 1-5` | the 1st, 11th, 21st and 31st, **and** only when a weekday |
| `0 9 1 * 0-7` | the 1st **or** any day — so every day, because `0-7` is every day yet is not a star |

croniter calls this the cron bug and hides it behind `implement_cron_bug`;
Vixie cron, ISC cron and Debian's cron all behave this way, so cron-translate
models it — in `convert` and in the plain `cron-translate EXPRESSION` next-run
times alike. If you have compared this tool against a library that reports
`0 9 */10 * 1-5` as "every tenth day or every weekday", that is the
disagreement, and the crontab on the box sides with this tool.

## Kubernetes CronJob

The same five fields, as parsed by robfig/cron v3 behind `spec.schedule`, with
two differences that bite:

- day-of-week is **0-6 only**. The `7` that vixie also reads as Sunday is a
  parse error, so `0 0 * * 7` converts to `0 0 * * 0`.
- there is no `L`, `W`, `?` or `#`.

The timezone is `spec.timeZone` on the CronJob (Kubernetes 1.27+), not part of
the expression; `CRON_TZ=` and `TZ=` inside `spec.schedule` are not supported.
With no `spec.timeZone`, a CronJob runs in the kube-controller-manager's zone,
which is usually — but not guaranteed to be — UTC.

## AWS EventBridge

Six fields, `minute hour day-of-month month day-of-week year`, with no
seconds.

| Field | Values | Accepts |
|---|---|---|
| minute | 0-59 | `,` `-` `*` `/` |
| hour | 0-23 | `,` `-` `*` `/` |
| day-of-month | 1-31 | `,` `-` `*` `?` `/` `L` `W` |
| month | 1-12, `JAN`-`DEC` | `,` `-` `*` `/` |
| day-of-week | 1-7, `SUN`-`SAT`, **1 = Sunday** | `,` `-` `*` `?` `L` `#` |
| year | 1970-2199 | `,` `-` `*` `/` |

The rules that make conversions fail rather than drift:

- day-of-month and day-of-week cannot both carry a value: one of them must be
  `?`.
- day-of-week does **not** take `/`.
- a `#` term must be the only term in its field — `3#1,6#3` is read as two
  expressions and rejected.
- `L-n` and `LW` are Quartz spellings, not EventBridge ones.

A `cron(...)` wrapper around the six fields is accepted and stripped.

## Quartz

Six or seven fields, `second minute hour day-of-month month day-of-week
[year]`. The year defaults to `*` and stops at 2099.

Day-of-week is 1-7 with **1 = Sunday**, the same as EventBridge and one off
from vixie — the mistake that shifts a whole schedule by a day and still looks
plausible. Exactly one of the day fields must be `?`, as in EventBridge.

Quartz has the largest vocabulary, which is why it is the dialect most likely
to convert *out of*: `L` (last day of the month), `L-n` (n days before it),
`LW` (last weekday), `nW` (weekday nearest day n, never leaving the month),
`nL` (last given weekday of the month) and `n#m` (the mth given weekday).

## systemd `OnCalendar=`

`DOW Y-M-D H:M:S [TZ]`, with `*` for any value, `,` for lists, `..` for
ranges, `/` for repetition and `~n` counting back from the end of the month
(`~01` is the last day). The `minutely`, `hourly`, `daily`, `weekly`,
`monthly`, `quarterly`, `semiannually`, `yearly` and `annually` shorthands are
accepted.

Two things set it apart from every cron dialect:

- the weekday and the date must **both** match. `Mon *-*-01` is "the 1st,
  when the 1st is a Monday" — not "every Monday and every 1st". A cron
  expression that settles for a match on either day field therefore has no
  `OnCalendar=` equivalent, and vice versa. One that requires both, because a
  field carries a star (`0 9 */10 * 1-5`), converts fine.
- it carries its own timezone as a suffix.

`W` (nearest weekday) and `#` (nth weekday) have no systemd spelling at all.

## What refuses, and why

| Source has | Target | Result |
|---|---|---|
| seconds other than `:00` | vixie, k8s, eventbridge | exit 65, `:00` form offered as *not* equivalent |
| `#` (nth weekday) | vixie, k8s, systemd | exit 65 |
| `L` / `L-n` / `nL` | vixie, k8s | exit 65 |
| `L-n`, `LW` | eventbridge | exit 65 — Quartz spellings |
| `W` (nearest weekday) | vixie, k8s, systemd | exit 65 |
| a restricted year | vixie, k8s | exit 65 |
| a year past 2099 | quartz | exit 65 |
| both day fields restricted | eventbridge, quartz | exit 65 — neither can leave both without a `?` |
| both day fields restricted, either enough (no star) | systemd | exit 65 — `OnCalendar=` needs both |
| weekday required alongside a date (systemd) | cron dialects, where the rendering would settle for either | exit 65 |
| `/` in day-of-week | eventbridge | exit 65 |
| `#` alongside other day-of-week terms | eventbridge | exit 65 |

Everything else converts, and anything that converts but loses a nuance —
`?` becoming `*`, a timezone moving to a different place, the OR/AND reading
happening to agree because only one day field is restricted — prints a caveat
next to the answer.

Every conversion also prints the next runs of both expressions on one clock.
The target text is parsed back with the target dialect's own parser before
those runs are computed, so the second column is an independent check.
