# Convert Example

What it shows: moving one schedule between cron dialects, the caveats that
come with it, and the conversions that refuse.

## Run

```sh
# Quartz to EventBridge: the `?` rule and the 1 = Sunday day-of-week
cron-translate convert --from quartz --to eventbridge '0 0 12 ? * MON-FRI *'

# vixie to a systemd timer
cron-translate convert --from vixie --to systemd '*/15 9-17 * * 1-5'

# Quartz to Kubernetes: the timezone caveat names spec.timeZone
cron-translate convert --from quartz --to k8s '0 0 9 ? * 2-6 *'
```

## Conversions that refuse

Each of these exits `65` and says why, rather than printing something close:

```sh
# Seconds: vixie has no such field. Offers `0 12 * * 1-5` as NOT equivalent.
cron-translate convert --from quartz --to vixie '30 0 12 ? * MON-FRI *'

# The third Friday: vixie has no `#`.
cron-translate convert --from quartz --to vixie '0 0 12 ? * 6#3 *'

# Both day fields restricted: cron ORs them, and EventBridge cannot say that.
cron-translate convert --from vixie --to eventbridge '0 9 1 * 1-5'

# ...and the mirror image: systemd ANDs them, which no cron dialect says.
cron-translate convert --from systemd --to vixie 'Mon..Fri *-*-01 09:00:00'
```
