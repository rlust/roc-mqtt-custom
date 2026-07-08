# Changelog

## v2.5.0 (2026-07-08) — Aqua-Hot control + heat zones

### Added
- **Heat-zone climate entities** (instances 3–6): Front Heat (Aqua-Hot),
  Rear Heat (Aqua-Hot), Bay Heat (Aqua-Hot), Floor Heat. Heat-only cards
  (off/heat, no fan); target temperature writes `setpoint_heat_f` through the
  bridge, preserving the zone's cool setpoint.
- **Aqua-Hot Electric / Burner switches** (AC loads 212/210), created when
  Thermostat bridge mode is enabled. Commands go via AC_LOAD_COMMAND
  (0x1FFBE, arb 0x19FFBEF9); state from AC_LOAD_STATUS with **shed
  detection** (level 0xFC/0xFD = requested but shed by the energy manager,
  exposed as a `shed` attribute).
- Bridge: `rvcbridge/acload_control/<instance>` topic with
  `{"state": "on"|"off"}` payloads; instances restricted to profile
  `safety.allowed_acload_instances` (default 210, 212); rate-limited and
  audited like zone commands. New `--acload-control-topic` CLI flag.
- 6 new tests (55 total).

### Notes
- WATERHEATER_COMMAND (1FFF6) is deliberately NOT used — the Firefly G6
  ignores it (verified in CoachIQ). OFF latches; ON is a request the energy
  manager may shed.

## v2.4.0 (2026-07-08) — Thermostat control rewrite (CoachIQ findings)

Cross-checked our THERMOSTAT_COMMAND_1 path against the CoachIQ project
(https://github.com/carpenike/coachiq, Apache-2.0), whose climate control was
verified byte-for-byte on a live Entegra Aspire Firefly G6 bus. Three wire-level
bugs fixed, plus a state-cache redesign.

### Fixed
- **Setpoint encoding**: bytes 3–6 of THERMOSTAT_COMMAND_1 were encoded as
  °C×100; RV-C Table 5.3 requires uint16 in 1/32-K steps (raw=(°C+273)×32).
  72°F now encodes as 9447 (0x24E7), not 2222.
- **CAN arbitration ID**: frames were sent with the bare PGN (0x1FEF9) as the
  ID; now built as (priority 6 << 26) | (PGN << 8) | source 0xF9 = 0x19FEF9F9.
- **Fan speed scale**: was sent 0–100; RV-C uses half-percent 0–200
  (0xC8 = 100%). Default is now 0 (automatic), not 50.

### Added
- `rvc_climate_units.py`: shared RV-C climate conversions/enums (ported from
  CoachIQ backend/integrations/rvc/climate_units.py, Apache-2.0).
- Bridge state cache: subscribes to THERMOSTAT_STATUS_1 topics and fills
  unchanged fields from live zone state — a setpoint-only command no longer
  clobbers mode/fan with invented defaults. Zones never seen on the bus are
  NACKed (`no_status_seen`) unless `--allow-unseeded`.
- Command confirmation: after TX, the next matching status echo publishes
  `{"status": "confirmed"}` on the ack topic (DGN pair 1FEF9→1FFE2).
- Bridge CLI: `--source-address`, `--priority`, `--status-topics`,
  `--status-max-age`, `--allow-unseeded`, `--confirm-window`.
- HA integration: optional **Thermostat bridge mode** (Settings → RV-C →
  Configure) — climate entities publish absolute JSON commands
  (`{"setpoint_f": 72}`) to `rvcbridge/thermostat_control/<zone>` instead of
  the legacy learned-signature burst. Off by default; legacy behavior unchanged.
- Tests: `tests/test_climate_units.py`, `tests/test_thermostat_bridge.py`
  (25 cases: encoding round-trips, frame bytes, arb ID, state fill-in).

### Changed
- `thermostat_pgn_map_aspire.json`: corrected byte-field documentation and
  added TX metadata (priority/SA/arbitration ID).
- manifest version → 2.4.0.

## 2.3.3 - 2026-02-21

- Fixed climate entity zone mapping to ignore non-zone climate-like instances and prevent bogus entities (e.g., instance 81).
- Added canonical climate zone mapping in discovery:
  - `THERMOSTAT_STATUS_1/0|1|2` => Front/Mid/Rear
  - `AIR_CONDITIONER_STATUS/1|2|3` => Front/Mid/Rear (mapped to thermostat instances `0|1|2`)
- Climate entities now initialize with stable names: `AC Front`, `AC Mid`, `AC Rear`.

## 2.3.2 - 2026-02-21

- Fixed climate attribute/state mapping for thermostat status payloads:
  - `temperature` now maps from `setpoint temp cool F` when present.
  - `current_temperature` now maps from `ambient temp F` when available.
- Added explicit climate attributes:
  - `setpoint_cool_f`
  - `setpoint_heat_f`
- Keeps existing HVAC/fan command services unchanged.

## 2.3.1 - 2026-02-21

- Added explicit Front/Mid/Rear zone aliases to HA HVAC interface tooling (`--zone front|mid|rear` maps to instances `0|1|2`).
- Updated HA package template (`tools/hvac_mira_package.yaml`) with zone-specific shell commands/scripts for Mid and Rear setpoint controls.
- Updated Home Assistant HVAC interface docs with canonical zone/entity mapping.
- Bumped custom component manifest version to `2.3.1` for release alignment.

## 2.3.0 - 2026-02-21

- Added Mira/Firefly-focused HVAC command support in the custom component climate platform using learned `THERMOSTAT_COMMAND_1` signatures.
- Added climate entity services:
  - `step_temperature_up`
  - `step_temperature_down`
  - `set_fan_profile` (`auto|low|high`)
- Added fan mode support (`auto/low/high`) to climate entities and mapped reported RV-C fan mode+speed into Home Assistant fan state.
- Updated climate command path to publish signature bursts on `RVC/THERMOSTAT_COMMAND_1/<instance>` for better reliability under controller gating.
- Updated `services.yaml` and bumped integration manifest version to `2.3.0`.

## 2.2.0 - 2026-02-13

- Cut a standalone release for the refactored architecture so downstream installs can adopt the new flow without waiting for additional changes.
- Bumped the integration manifest to 2.2.0 to match the new release tag and HACS metadata requirements.
- Documented the architectural highlights (momentary lock buttons, dedicated switch/generator entities, availability mixin, restored climate/light state, config-entry options) as part of this release.

## 2.1.2 - 2026-02-11

- Added dedicated door-lock buttons (Lock + Unlock) so each RV-C command is exposed separately.
- Lock entities are now status-only; use the new buttons for momentary control while the lock entity shows the last reported state.

## 2.1.1 - 2026-02-11

- Door locks behave as momentary triggers and avoid staying latched in Locked/Unlocked when telemetry is missing.

## 2.1.0 - 2026-02-11

- Added relay switch support (satellite dome + water pump) with real `switch.` entities, RestoreEntity state, and availability timeouts.
- Added generator Start/Stop buttons so momentary RV-C commands no longer masquerade as lights.
- Lights now own the ramp services declared in `services.yaml`, restore brightness/on state after HA restarts, and keep using configurable command topics.
- All platforms (lights, covers, locks, climate, switches) inherit the new availability mixin so entities go unavailable when telemetry stops.
- Climate entities restore HVAC mode/temperatures on startup; README now documents the new options flow and features.

## 2.0.0 - 2026-02-11

- Added relay switch support (satellite dome + water pump) with real `switch.` entities, RestoreEntity state, and availability timeouts.
- Added generator Start/Stop buttons so momentary RV-C commands no longer masquerade as lights.
- Lights now own the ramp services declared in `services.yaml`, restore brightness/on state after HA restarts, and keep using configurable command topics.
- All platforms (lights, covers, locks, climate, switches) inherit the new availability mixin so entities go unavailable when telemetry stops.
- Climate entities restore HVAC mode/temps on startup; README now documents the new options flow and features.

## 2.0.0 - 2026-02-11

- Require Home Assistant 2025.1.0+ and expose the version in `manifest.json` for HACS.
- Store topic prefix / auto-discovery flags in config-entry options and add a migration helper so existing installs pick them up automatically.
- Wire config-entry update listeners so editing options triggers a clean reload instead of requiring a manual remove/re-add.
- Make every platform read settings from entry options (lights, covers, locks, climate) and keep defaults consistent in the options flow.

## 1.0.0

- Initial release of RV-C custom integration.
- MQTT-based discovery for lights, climate, and sensors.
- Dimmer naming based on instance mapping.
- Command topic for dimmers with CC and brightness percent.
