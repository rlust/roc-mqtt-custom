"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
    path.join(__dirname, "mapped-light-retained-status.js"),
    "utf8",
);
const transform = new Function("msg", source);

const mappedInstances = [
    ...range(25, 42),
    ...range(45, 47),
    ...range(51, 54),
    ...range(56, 60),
];

assert.equal(mappedInstances.length, 30);
for (const instance of mappedInstances) {
    const payload = {instance, name: "DC_DIMMER_STATUS_3"};
    const result = transform({
        topic: `RVC/DC_DIMMER_STATUS_3/${instance}`,
        payload,
    });
    assert.equal(result.topic, `RVC/status/light/${instance}`);
    assert.strictEqual(result.payload, payload);
}

for (const instance of [24, 43, 44, 48, 49, 50, 55, 61, 181]) {
    assert.equal(
        transform({
            topic: `RVC/DC_DIMMER_STATUS_3/${instance}`,
            payload: {instance},
        }),
        null,
    );
}

for (const topic of [
    "RVC/status/light/28",
    "RVC/DC_DIMMER_STATUS_3/not-a-number",
    "RVC/DC_DIMMER_STATUS_2/28",
    "node-red/rvc/commands",
    "",
]) {
    assert.equal(transform({topic, payload: {instance: 28}}), null);
}

console.log("mapped-light retained-status tests passed");

function range(start, end) {
    return Array.from({length: end - start + 1}, (_, index) => start + index);
}
