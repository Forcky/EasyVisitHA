# EasyVisit GP Availability for Home Assistant

[![Validate](https://github.com/Forcky/EasyVisitHA/actions/workflows/validate.yml/badge.svg)](https://github.com/Forcky/EasyVisitHA/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

Get a notification on your phone as soon as an appointment opens up with **your** GP.

Many Australian practices take online bookings through [EasyVisit](https://www.easyvisit.com.au). Popular GPs are often booked out for weeks, and cancellations are gone within minutes. This integration watches the practice's booking page. When a slot with the doctor you choose opens up before your cutoff, you get an alert, and tapping it opens the booking page.

- **No login needed.** It reads the same public availability the booking page shows.
- **Light on the API.** One request per check covers every doctor at the practice.
- **Watch as many doctors as you like**, each with their own cutoff, plus an optional *Any doctor* watch.
- **Announces each slot once.** If someone books a slot and it later reopens, you hear about it again.
- **Automation-friendly.** Every new slot fires an `easyvisit_slot_available` event.
- **Handles Tasmanian daylight saving** and other Australian time zones.

> Not affiliated with EasyVisit or Sonic Healthcare. It uses an undocumented API that may change without notice.

## Quick start

1. **Install:** HACS → ⋮ → *Custom repositories* → add `https://github.com/Forcky/EasyVisitHA` as an **Integration**. Download **EasyVisit GP Availability**, then restart Home Assistant.
2. **Add:** Settings → Devices & services → *Add integration* → **EasyVisit GP Availability**.
3. **Paste the booking link** from the practice's EasyVisit page, e.g. `https://web.easyvisit.com.au/booking/123/456`.
4. **Pick the appointment type and your doctor(s),** plus the notify service for your phone (e.g. `notify.mobile_app_pixel_8`).
5. **Test it:** press **Send test notification** on the doctor's device.

## What you get (per doctor)

| Entity | Description |
|---|---|
| **Next available** | The earliest open slot (timestamp), with the next 10 slots and the doctor's notes as attributes |
| **Slots before cutoff** | How many open slots fall on or before the cutoff date |
| **Slot before cutoff** | Binary sensor, on when anything is open before the cutoff |
| **Cutoff** | Days ahead that count as soon enough (default 14; *Any doctor* defaults to 2) |
| **Notifications** | Turn alerts for this doctor on or off |
| **Send test notification** | Sends what is open before the cutoff right now |

## Documentation

- [Installation](docs/installation.md): HACS, manual install, updating, removing
- [Configuration](docs/configuration.md): setup, options, entities, choosing a cutoff
- [Notifications and automations](docs/notifications.md): how alerts are decided, the event, example automations and dashboard cards
- [Troubleshooting](docs/troubleshooting.md)
- [Development](docs/development.md): architecture, tests, releasing
- [API notes](API.md): the reverse-engineered EasyVisit API
- [Roadmap](docs/roadmap.md): opt-in auto-booking (phase 2)

## Licence

MIT. See [LICENSE](LICENSE).
