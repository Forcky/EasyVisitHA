# Installation

Requires Home Assistant **2026.8** or newer.

## HACS (recommended)

1. In Home Assistant open **HACS**, then **⋮** (top right) → **Custom repositories**.
2. Repository: `https://github.com/Forcky/GPAvailabilityHA`, type: **Integration** → **Add**.
3. Search HACS for **GP Availability** → **Download**. Pick the latest version.
4. Restart Home Assistant (Settings → System → ⏻ → Restart).
5. Settings → Devices & services → **Add integration** → **GP Availability**. See [Configuration](configuration.md).

HACS will offer updates as new releases are published.

## Manual

1. Download the latest release, or clone the repository.
2. Copy `custom_components/gp_availability/` into your Home Assistant config directory, so that you end up with `<config>/custom_components/gp_availability/manifest.json`.
3. Restart Home Assistant and add the integration as above.

To update, replace the folder and restart.

## Notifications prerequisite

To get alerts on your phone, install the **Home Assistant companion app** and sign in. HA then creates a notify service such as `notify.mobile_app_<your_phone>`. Any other notify service works too, e.g. Telegram, Pushover, or email.

## Moving from EasyVisit GP Availability 0.1.x

Version 0.2.0 renamed the integration from `easyvisit` to `gp_availability` when HotDoc support was added. Home Assistant treats it as a new integration, so move over once:

1. **Note your settings:** the watched doctors, cutoffs, notify services and check interval.
2. **Delete the old entry:** Settings → Devices & services → EasyVisit GP Availability → ⋮ → **Delete**. Do this first, so the new entities can take the same entity IDs.
3. **Remove the old download** in HACS (EasyVisit GP Availability → ⋮ → **Remove**), and the old custom repository if HACS still lists it. Or delete `custom_components/easyvisit/`.
4. **Install GP Availability** as above and restart.
5. **Add the practice again** with the same link, then set the cutoffs again.

Automations that listened for `easyvisit_slot_available` must use `gp_availability_slot_available`. The event data now uses `practice_id` instead of `location_id`, watch ids are strings (`"any"` instead of `0` for *Any doctor*), and there is a new `provider` field.

## Removing

Settings → Devices & services → GP Availability → ⋮ → **Delete**. Then remove it in HACS, or delete `custom_components/gp_availability/`, and restart.
