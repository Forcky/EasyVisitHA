# Development

## Architecture

```
custom_components/easyvisit/
  api.py          aiohttp client; unwraps {StatusCode, Message, Data}; strips photoData/bio
  slots.py        pure logic, no HA imports: parse, localise, cutoff, "already announced" diff
  coordinator.py  DataUpdateCoordinator: one resources call per poll, per-watch data,
                  announcements (event + notify services), settings in a Store
  entity.py       per-watch device (via_device_id -> practice device)
  sensor.py  binary_sensor.py  number.py  switch.py  button.py
  config_flow.py  practice -> appointment type -> doctors/notify/interval; options flow
```

- **Data flow:** `resources` API → `parse_resources` → `slots_for_watch` → `qualifying` → `diff_seen` → announce.
- **`coordinator.data`:** `{"doctors": {resourceId: {...}}, "watches": {watch_id: {"slots", "qualifying", "cutoff"}}}`.
- **Store `easyvisit.<entry_id>`:** holds `{"watches": {"<id>": {"cutoff_days", "notify", "seen"}}}`. `seen: null` means the watch hasn't polled yet, so its first poll is silent.
- **Config entry:** `data` holds the location and appointment type. `options` holds `watches` (`{"<resourceId>": "<name>"}`, with `"0"` for any doctor), `notify_targets` and `scan_interval`.

The API is described in [API.md](../API.md).

## Running the tests

The tests use [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component), which runs a real Home Assistant core. **It needs Linux or macOS**, because HA imports `fcntl`. On Windows, use WSL.

```bash
uv venv -p 3.14 .venv && source .venv/bin/activate   # or: python3.14 -m venv .venv
pip install -r requirements_test.txt
pytest -q
```

| File | Covers |
|---|---|
| `tests/test_slots.py` | Parsing, DST, cutoff edges, re-announce logic |
| `tests/test_init.py` | Entities, silent first poll, notifications once and again after reopening, mute switch, cutoff changes, test button, settings across reload, options flow pruning devices |
| `tests/test_config_flow.py` | Link parsing, full flow, validation errors |

The fixture `tests/fixtures/resources_sample.json` is an anonymised real response (3 doctors; names, notes and IDs replaced). The clock is frozen at 27 Sep 2026 10:00 Hobart.

## CI

`.github/workflows/validate.yml` runs on push, on PRs, and daily. It has three jobs:
- **HACS validation**
- **hassfest**:
  - `manifest.json` keys must be ordered `domain`, `name`, then alphabetical.
  - Translation strings must not contain URLs; pass them via `description_placeholders`.
- **pytest**

## Releasing

1. Bump `version` in `custom_components/easyvisit/manifest.json`.
2. Commit, tag `vX.Y.Z`, push the tag.
3. `gh release create vX.Y.Z --generate-notes`.

HACS offers the new release to users.

## Translations

`strings.json` is the source. Copy it to `translations/en.json` whenever it changes.
