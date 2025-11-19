# 🎉 v1.1.0 - Core Functionality Improvements

## Phase 1 Complete: Climate Commands, Sensor Extraction, Ramp Services

This release brings full two-way control to climate entities, comprehensive sensor field extraction, and adds ramp services for smooth light transitions.

---

## 🌡️ Climate Platform - Now Fully Controllable

**New Features:**
- ✅ **Temperature setpoint commands** - Set your desired temperature from Home Assistant
- ✅ **HVAC mode control** - Switch between OFF, COOL, HEAT, and AUTO modes
- ✅ **RV-C operating mode mapping** - Proper translation to RV-C protocol (off=0, cool=1, heat=2, auto=3)
- ✅ **Command topic**: `{prefix}/command/climate/{instance}`

**Technical Details:**
- MQTT command publishing implemented for both `async_set_temperature()` and `async_set_hvac_mode()`
- Includes both numeric and string formats for bridge compatibility
- Proper state management and UI updates

---

## 📊 Sensor Platform - Complete Field Extraction

**Major Rewrite:**
Replaced generic sensor framework with comprehensive RV-C field extraction supporting multiple sensors from single MQTT messages.

**Supported Sensors:**

| Sensor Type | Fields | Device Class | Unit |
|---|---|---|---|
| **Tank Status** | Relative level, tank type | - | % |
| **Thermostat Ambient** | Ambient temperature | Temperature | °F/°C |
| **Inverter DC** | DC voltage, DC current | Voltage, Current | V, A |
| **Inverter AC** | AC frequency | Frequency | Hz |
| **Inverter Temperature** | FET temp, transformer temp | Temperature | °C |
| **AC Load** | Load percentage | Power Factor | % |
| **Charger** | Charger state | - | - |

**Key Improvements:**
- ✅ **Proper device classes** - Ready for Home Assistant energy dashboard
- ✅ **State classes** - Enables long-term statistics and graphing
- ✅ **Friendly names** - e.g., "Fresh Tank Level", "Zone 1 Ambient Temperature"
- ✅ **Multiple sensors per message** - DC voltage AND current from single INVERTER_DC_STATUS
- ✅ **Fallback support** - Still works with generic "value" payloads

---

## 💡 Light Platform - Ramp Services

**New Services:**
- ✅ `rvc.ramp_up` - Smoothly increase brightness over time
- ✅ `rvc.ramp_down` - Smoothly decrease brightness over time

**Features:**
- Configurable duration (1-60 seconds)
- RV-C command codes: CC_RAMP_UP (0x03), CC_RAMP_DOWN (0x04)
- Logging for troubleshooting

**Usage Example:**
```yaml
service: rvc.ramp_up
data:
  entity_id: light.living_room_vanity_e
  duration: 5
```

---

## 🔧 Technical Changes

**Modified Files:**
- `climate.py` - MQTT command publishing
- `sensor.py` - Complete field extraction rewrite (+194 lines)
- `light.py` - Ramp service methods
- `services.yaml` - Ramp service definitions
- `__init__.py` - Code cleanup
- `manifest.json` - Version bump to 1.1.0

**Code Quality:**
- Proper type hints throughout
- Comprehensive documentation
- Backward compatible with existing payloads
- Clean separation of concerns

---

## 📦 Installation

### Via HACS:
1. **HACS** → **Integrations** → Find **"RV-C Integration"**
2. Click **"Update"** (if already installed)
3. Restart Home Assistant

### New Installation:
1. **HACS** → **Integrations** → **⋮** → **Custom repositories**
2. Add: `https://github.com/rlust/roc-mqtt-custom`
3. Category: **Integration**
4. Install **"RV-C Integration"**
5. Restart Home Assistant
6. **Settings** → **Devices & Services** → **Add Integration** → **RV-C**

---

## 🚀 What's Next

**Coming Soon:**
- Phase 2: Expanded device name mappings
- Phase 3: Cover platform for slides/awnings
- Phase 4: Multi-message correlation for climate entities
- Additional platforms: Switch (pumps), Binary Sensor (generator)

---

## 📚 Documentation

- **Installation Guide**: [INSTALL.md](https://github.com/rlust/roc-mqtt-custom/blob/main/INSTALL.md)
- **Project Roadmap**: [RVC_PROJECT_NOTES.md](https://github.com/rlust/roc-mqtt-custom/blob/main/RVC_PROJECT_NOTES.md)
- **Issues**: Report bugs at https://github.com/rlust/roc-mqtt-custom/issues

---

**Full Changelog**: https://github.com/rlust/roc-mqtt-custom/compare/v1.0.0...v1.1.0

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
