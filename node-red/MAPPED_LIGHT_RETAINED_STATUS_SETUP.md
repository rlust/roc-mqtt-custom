# Restart-safe mapped-light status

RV-C dimmers may publish `DC_DIMMER_STATUS_3` only when their physical state
changes. After Home Assistant restarts or reloads the RV-C integration, mapped
lights therefore remain unavailable until another genuine status frame arrives.

Use the function in [`mapped-light-retained-status.js`](mapped-light-retained-status.js)
to retain genuine mapped status on a separate MQTT namespace:

```text
RVC/DC_DIMMER_STATUS_3/<instance>
                  |
                  v
mapped-light-retained-status.js
                  |
                  v
RVC/status/light/<instance>  (retained)
```

The separation is the safety boundary. The input subscription cannot consume
the retained output, so historical values cannot circulate as a feedback loop.
The RV-C integration already subscribes to `RVC/#` and recognizes the standard
`RVC/status/light/<instance>` layout.

## Node-RED configuration

1. Add an MQTT input subscribed only to `RVC/DC_DIMMER_STATUS_3/+` on the broker
   used by Home Assistant.
2. Add a Function node and paste the complete contents of
   `mapped-light-retained-status.js`.
3. Add an MQTT output on the same broker with:
   - Topic: blank, so the function's `msg.topic` is used
   - QoS: `0`
   - Retain: `true`
4. Wire only input → function → output.
5. Export or back up the current flow, then deploy only the affected nodes.

The function allows the 30 state-backed mapped instances: 25–42, 45–47,
51–54, and 56–60. It deliberately excludes registry-only instance 44, mapping
gaps, awning controls 49/50, and unrelated dimmers.

If the configured RV-C topic prefix is not uppercase `RVC`, replace `RVC` in
both the input subscription and function before deployment. The input and
output prefixes must match the Home Assistant integration option.

## Seed and verify

The retained namespace starts empty. Populate it only from genuine
`DC_DIMMER_STATUS_3` frames produced by physical controls or an explicitly
authorized lights-only command test.

Verify all of the following:

1. A fresh MQTT subscriber receives one retained
   `RVC/status/light/<instance>` record per proven mapped light.
2. Reload only the RV-C config entry. Do not restart Home Assistant merely to
   test this flow.
3. Confirm mapped entities recover from retained status with an MQTT timestamp
   and no pending command.
4. Run one non-safety light ON/OFF canary, require matching physical status for
   both commands, and leave it OFF.
5. Observe both namespaces. A quiet coach should show retained replay once per
   safe topic and no repeated mapped source traffic.

Never retain `node-red/rvc/commands` or any other command topic.

## Rollback

Restore the pre-change Node-RED flow backup using the current flow revision.
Then clear only the retained `RVC/status/light/<instance>` records created by
this flow. Verify that the function wiring is absent, command wiring is
unchanged, and a fresh subscriber receives no safe-namespace retained records.
