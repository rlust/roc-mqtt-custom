/*
Node-RED Function: RV-C THERMOSTAT_COMMAND_1 (PGN 0x1FEF9) handler

Purpose
- Accept thermostat commands from either:
  1) rvcbridge/thermostat_control/<instance>   (JSON control payload)
  2) RVC/THERMOSTAT_COMMAND_1/<instance>       (pre-built handoff payload)
- Build CAN frame bytes for THERMOSTAT_COMMAND_1 (DGN 1FEF9)
- Output payload for your CAN TX node

Function outputs
- Output 1: CAN TX message (to your existing CAN transmitter path)
- Output 2: Status/debug (optional)

Expected output payload (Output 1)
{
  "name": "THERMOSTAT_COMMAND_1",
  "dgn": "1FEF9",
  "instance": 0,
  "data": "00012108080808FF",
  "setpoint_f": 69,
  "mode": 1,
  "fan_mode": 0,
  "fan_speed": 33
}

If your CAN node expects another shape, map msg.payload there.
*/

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function fToC100(f) {
  return Math.round(((f - 32) * 5 / 9) * 100);
}

function toHexByte(n) {
  return (n & 0xFF).toString(16).toUpperCase().padStart(2, '0');
}

function parseInstanceFromTopic(topic) {
  if (!topic) return null;
  const parts = topic.split('/');
  if (parts.length < 3) return null;
  const maybe = parts[parts.length - 1];
  const i = Number(maybe);
  return Number.isInteger(i) ? i : null;
}

function buildDataHex(instance, mode, fanMode, fanSpeed, heatC100, coolC100) {
  // Byte layout for thermostat command/status style payload:
  // b0 instance
  // b1 mode(0..3 bits) + fanMode(4..5 bits) + schedule(6..7 bits=0)
  // b2 fan speed %
  // b3,b4 heat setpoint (LE, c*100)
  // b5,b6 cool setpoint (LE, c*100)
  // b7 reserved=0xFF
  const b0 = instance;
  const b1 = (mode & 0x0F) | ((fanMode & 0x03) << 4);
  const b2 = fanSpeed;
  const b3 = heatC100 & 0xFF;
  const b4 = (heatC100 >> 8) & 0xFF;
  const b5 = coolC100 & 0xFF;
  const b6 = (coolC100 >> 8) & 0xFF;
  const b7 = 0xFF;

  return [b0, b1, b2, b3, b4, b5, b6, b7].map(toHexByte).join('');
}

const topic = msg.topic || "";
let p = msg.payload;

if (typeof p === 'string') {
  try { p = JSON.parse(p); } catch (e) { p = { raw: msg.payload }; }
}
if (!p || typeof p !== 'object') p = {};

// If already pre-built handoff payload, pass through with normalization.
if ((p.name === 'THERMOSTAT_COMMAND_1' || p.dgn === '1FEF9') && p.data) {
  const out = {
    topic: `RVC/THERMOSTAT_COMMAND_1/${p.instance ?? parseInstanceFromTopic(topic) ?? 0}`,
    payload: {
      name: 'THERMOSTAT_COMMAND_1',
      dgn: '1FEF9',
      instance: Number(p.instance ?? parseInstanceFromTopic(topic) ?? 0),
      data: String(p.data).toUpperCase(),
      mode: Number(p.mode ?? 1),
      fan_mode: Number(p.fan_mode ?? p['fan mode'] ?? 0),
      fan_speed: Number(p.fan_speed ?? p['fan speed'] ?? 35)
    }
  };

  const dbg = {
    topic: 'rvcbridge/thermostat_control/handler_status',
    payload: {
      status: 'pass_through',
      source_topic: topic,
      out_topic: out.topic,
      ts: Date.now()
    }
  };

  return [out, dbg];
}

// Build from control payload format.
const instance = clamp(Number(p.instance ?? parseInstanceFromTopic(topic) ?? 0), 0, 6);
const mode = clamp(Number(p.mode ?? 1), 0, 4);          // 0 off,1 cool,2 heat,3 auto,4 fan
const fanMode = clamp(Number(p.fan_mode ?? 0), 0, 1);   // 0 auto, 1 on
const fanSpeed = clamp(Number(p.fan_speed ?? 35), 0, 100);

const setpointF = p.setpoint_f !== undefined ? Number(p.setpoint_f) : undefined;
const heatF = p.setpoint_heat_f !== undefined ? Number(p.setpoint_heat_f) : setpointF;
const coolF = p.setpoint_cool_f !== undefined ? Number(p.setpoint_cool_f) : setpointF;

const heatC100 = p.setpoint_heat_c !== undefined
  ? Math.round(Number(p.setpoint_heat_c) * 100)
  : fToC100(heatF !== undefined ? heatF : 69);

const coolC100 = p.setpoint_cool_c !== undefined
  ? Math.round(Number(p.setpoint_cool_c) * 100)
  : fToC100(coolF !== undefined ? coolF : 69);

const dataHex = buildDataHex(instance, mode, fanMode, fanSpeed, heatC100, coolC100);

const out = {
  topic: `RVC/THERMOSTAT_COMMAND_1/${instance}`,
  payload: {
    name: 'THERMOSTAT_COMMAND_1',
    dgn: '1FEF9',
    instance,
    data: dataHex,
    setpoint_f: setpointF,
    mode,
    fan_mode: fanMode,
    fan_speed: fanSpeed
  }
};

const dbg = {
  topic: 'rvcbridge/thermostat_control/handler_status',
  payload: {
    status: 'built',
    source_topic: topic,
    out_topic: out.topic,
    data: dataHex,
    ts: Date.now()
  }
};

return [out, dbg];
