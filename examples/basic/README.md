# Basic Example

What it shows: describing a cron expression and listing its next runs in a
specific timezone, including a DST warning.

## Run

```sh
cron-translate '*/15 9-17 * * 1-5'
cron-translate '30 2 * * *' --tz America/New_York --next 3
```
