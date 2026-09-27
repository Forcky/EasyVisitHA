# AGENTS.md

Guidance for agents working in this repository.

## What this repo is

A Home Assistant custom integration (HACS-installable, domain `easyvisit`). It polls a practice's public EasyVisit availability and notifies when a watched doctor has a slot before a cutoff. Everything lives in `custom_components/easyvisit/`. The API is documented in `API.md`; read it before touching `api.py` or `slots.py`.

## Layout

- `api.py`: a pure aiohttp client. It unwraps the `{StatusCode, Message, Data}` envelope and drops `photoData`/`bio`.
- `slots.py`: **no Home Assistant imports**. It holds slot parsing (naive local time + Windows zone name → aware datetime), cutoff matching, and the "already announced" diff. Put pure logic here so it stays easy to test.
- `coordinator.py`: one resources call per poll. It builds per-watch data and runs `_announce` (event + notify services). Per-watch settings (`cutoff_days`, `notify`, `seen`) live in a `helpers.storage.Store`, **not** the config entry, so changing them from an entity doesn't reload the integration. `seen: None` marks a watch that hasn't polled yet; that first poll is silent.
- `entity.py`: one device per watch (`<entry_id>_<resourceId>`, with `0` = any doctor), linked by `via_device_id` to a practice device that `__init__.py` creates first. `via_device` (identifier tuple) is deprecated since 2026.8, hence `hacs.json`'s minimum HA version.
- Platforms: `sensor`, `binary_sensor`, `number` (cutoff), `switch` (notifications), `button` (test notification).
- `config_flow.py`: practice (ID or booking link) → appointment type → doctors + notify targets + interval. The options flow edits the same fields and reloads. The watch list is stored in options as `{"<resourceId>": "<name>"}`.

## Validating changes

The tests need Linux or macOS, because HA imports `fcntl`. On Windows, run them in WSL:

```bash
# once: uv venv -p 3.14 ~/.venvs/easyvisit && VIRTUAL_ENV=~/.venvs/easyvisit uv pip install -r requirements_test.txt
cd <repo> && ~/.venvs/easyvisit/bin/python -m pytest -q -p no:cacheprovider
```

- `tests/test_slots.py` covers the pure logic.
- `tests/test_init.py` / `tests/test_config_flow.py` run a real HA through `pytest-homeassistant-custom-component`, with the API patched and a frozen clock (27 Sep 2026 10:00 Hobart).
- The fixture `tests/fixtures/resources_sample.json` is an anonymised real response (3 doctors; names, notes and IDs replaced, real slot times kept).

CI (`.github/workflows/validate.yml`) runs HACS, hassfest and pytest. hassfest rules that trip easily:
- `manifest.json` keys must be ordered `domain`, `name`, then alphabetical.
- No translation string may contain a literal URL. Pass URLs through `description_placeholders`.

## Gotchas

- Slot `dateTime` is naive local time. Always localise it with the zone from `timeZoneId`, never a fixed offset; Tasmania changes to DST on the first Sunday of October.
- The Any-doctor watch at a busy practice has hundreds of qualifying slots. Keep it muted by default, with a short default cutoff.
- Auto-booking (phase 2) must never double-book. Plan: lock → ValidateMultipleBooking → book → turn the auto-book switch off. See API.md for the unresolved `Token` field.
