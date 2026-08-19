// Node-RED Function node: map genuine RV-C dimmer status into a retained,
// non-looping Home Assistant status namespace.
//
// Input:  RVC/DC_DIMMER_STATUS_3/<instance>
// Output: RVC/status/light/<instance>
//
// Configure the downstream MQTT output with a blank topic, QoS 0, and Retain
// enabled. Never point this function's input at RVC/# or RVC/status/light/+.

const match = /^RVC\/DC_DIMMER_STATUS_3\/(\d+)$/.exec(msg.topic || "");
if (!match) return null;

const instance = Number(match[1]);
const mapped =
    (instance >= 25 && instance <= 42) ||
    (instance >= 45 && instance <= 47) ||
    (instance >= 51 && instance <= 54) ||
    (instance >= 56 && instance <= 60);
if (!mapped) return null;

msg.topic = `RVC/status/light/${instance}`;
return msg;
