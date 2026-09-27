# Troubleshooting

## No notification arrived

1. **Press "Send test notification"** on the doctor's device.
   - If nothing arrives, the notify service is the problem. Check **Configure → Notify services**, and try the same service in Developer tools → Actions.
   - If it arrives, the integration and phone are fine. There simply hasn't been a *new* slot before the cutoff.
2. Check that **Notifications** is on for that doctor. *Any doctor* starts off.
3. Remember the **first check after adding a doctor is silent**. Slots already open are only announced once they reopen, or if you raise the cutoff to include them.
4. Look at **Slots before cutoff**. If it's above 0, those slots have already been announced.
5. On Android, check that the companion app is allowed to show notifications and isn't battery-restricted.

## "Location not found" during setup

Use the number right after `/booking/` in the practice's booking link, or paste the whole link. EasyVisit may also be temporarily unreachable; try again shortly.

## Entities are unavailable

The last check failed. EasyVisit may be down, or Home Assistant may have no internet. The integration retries on the next interval. **Cutoff** and **Notifications** stay usable while it retries. Check the logs as described below.

## Slot times look an hour off

Times are converted from the practice's own zone (EasyVisit reports e.g. *Tasmania Standard Time*). Make sure Settings → System → General has the right time zone for **your** Home Assistant. Entities are stored in UTC and displayed in HA's zone.

## A doctor shows "Not listed for this appointment type right now"

The practice has stopped offering that appointment type for the doctor, or has hidden them online. They remain watched and come back automatically if they reappear.

## Debug logs

Add this to `configuration.yaml` and restart, or use the integration's **Enable debug logging**:

```yaml
logger:
  logs:
    custom_components.easyvisit: debug
```

Then filter Settings → System → Logs by `easyvisit`. Each announcement logs `"<doctor>: N new slot(s) by <date>"` at info level.

## Reporting an issue

Open an issue at <https://github.com/Forcky/EasyVisitHA/issues> with your HA version, the integration version, and debug logs. Remove anything personal first.
