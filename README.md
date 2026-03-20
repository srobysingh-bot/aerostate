# AeroState

AeroState is a Home Assistant custom integration that exposes supported IR air conditioners as native climate entities.

Release: v1.0.0

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Add AeroState as a custom integration source: https://github.com/srobysingh-bot/aerostate
3. Install AeroState.
4. Restart Home Assistant.
5. Add AeroState from Devices and Services.

### Manual install

1. Copy custom_components/aerostate into your Home Assistant config under custom_components/.
2. Restart Home Assistant.
3. Add AeroState from Devices and Services.

## Verified Production Scope

- Transport: Broadlink remote entities
- Active production pack: lg.pc09sq_nsj.protocol.v1
- Model: LG PC09SQ NSJ (protocol path)
- Verified HVAC modes: auto, cool, heat, dry, fan_only
- Verified temperature range: 16-30 C
- Verified fan levels: auto, low, mid, high, highest
- Vertical swing: verified and exposed
- Horizontal swing: verified in currently supported form (off/on)
- Throughput path: debounce + latest-state-wins + serialized send

## Intentionally Disabled (Conservative by Design)

- Jet/Turbo preset is disabled until model-specific ON/OFF frames are verified.
- Advanced horizontal positions (left/center/right) are hidden until verified for this model.

## Setup Recommendations

1. Select the correct Broadlink remote entity in config flow.
2. Select lg.pc09sq_nsj.protocol.v1.
3. Optionally link room temperature, humidity, and power sensors.
4. Run onboarding validation.
5. Add the created climate entity to a dashboard thermostat card.

## Troubleshooting

### Remote unavailable

- Confirm remote.send_command service exists.
- Check the selected remote entity state is not unavailable/unknown.
- Verify Broadlink placement and line-of-sight to AC.

### Commands not reflected on AC

- Confirm the configured model pack is lg.pc09sq_nsj.protocol.v1.
- Check diagnostics for support_summary, pack limitations, and validation readiness.
- Re-run the self-test service and review Home Assistant logs for aerostate warnings.

### Linked sensor issues

- If linked sensors are missing or unavailable, AeroState remains controllable.
- Repair issues will be raised for missing linked sensors to simplify support.

## Self-Test Service

Service: aerostate.run_self_test

- Use entry_id or entity_id to target an AeroState entry.
- profile: basic runs a minimal safe set.
- profile: full runs additional supported states.

Example:

```yaml
service: aerostate.run_self_test
data:
  entity_id: climate.aerostate_lg_pc09sq_nsj
  profile: full
```

## Support Policy

- AeroState only exposes capabilities that are encoded and verified for the selected pack.
- Unsupported features are hidden rather than simulated.
- Diagnostics include pack notes and limitations for fast support triage.

## Links

- Pack authoring guide: PACK_AUTHORING_GUIDE.md
- Changelog: CHANGELOG.md
- Release notes: RELEASE_NOTES.md
