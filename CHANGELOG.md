# Changelog

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
