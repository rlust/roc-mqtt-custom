# Node-RED Thermostat Handler Setup (Aspire RV-C)

## Goal
Convert MQTT thermostat control messages into `THERMOSTAT_COMMAND_1` (`DGN 1FEF9`) payloads your existing CAN TX path can send.

## File
- `node-red/thermostat-command-handler.js`

## Node-RED wiring

1. **MQTT in**
   - Topic(s):
     - `rvcbridge/thermostat_control/+`
     - `RVC/THERMOSTAT_COMMAND_1/+` (optional pass-through)

2. **Function**
   - Paste contents of `thermostat-command-handler.js`
   - Set function outputs to **2**

3. **Output 1** (CAN path)
   - Wire to your existing node that publishes/sends RV-C command payloads to CAN bridge.

4. **Output 2** (debug)
   - Wire to Debug node or MQTT out topic for status.

## What it emits
Output 1 topic:
- `RVC/THERMOSTAT_COMMAND_1/<instance>`

Output 1 payload example:
```json
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
```

## Test command
```bash
mosquitto_pub -h 192.168.100.234 -u rc -P rc \
  -t 'rvcbridge/thermostat_control/0' \
  -m '{"setpoint_f":69,"mode":1,"fan_mode":0,"fan_speed":33}'
```

## Expected
1. Debug output shows status `built` or `pass_through`
2. `RVC/THERMOSTAT_COMMAND_1/0` is published
3. CAN bridge transmits thermostat command
4. Thermostat setpoint changes physically

## Safety
- Instance clamped to `0..6`
- Mode clamped to `0..4`
- Fan mode clamped to `0..1`
- Fan speed clamped to `0..100`
