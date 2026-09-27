# Installation

Requires Home Assistant **2026.8** or newer.

## HACS (recommended)

1. In Home Assistant open **HACS**, then **⋮** (top right) → **Custom repositories**.
2. Repository: `https://github.com/Forcky/EasyVisitHA`, type: **Integration** → **Add**.
3. Search HACS for **EasyVisit GP Availability** → **Download**. Pick the latest version.
4. Restart Home Assistant (Settings → System → ⏻ → Restart).
5. Settings → Devices & services → **Add integration** → **EasyVisit GP Availability**. See [Configuration](configuration.md).

HACS will offer updates as new releases are published.

## Manual

1. Download the latest release, or clone the repository.
2. Copy `custom_components/easyvisit/` into your Home Assistant config directory, so that you end up with `<config>/custom_components/easyvisit/manifest.json`.
3. Restart Home Assistant and add the integration as above.

To update, replace the folder and restart.

## Notifications prerequisite

To get alerts on your phone, install the **Home Assistant companion app** and sign in. HA then creates a notify service such as `notify.mobile_app_<your_phone>`. Any other notify service works too, e.g. Telegram, Pushover, or email.

## Removing

Settings → Devices & services → EasyVisit GP Availability → ⋮ → **Delete**. Then remove it in HACS, or delete `custom_components/easyvisit/`, and restart.
