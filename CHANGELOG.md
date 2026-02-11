# Changelog

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
