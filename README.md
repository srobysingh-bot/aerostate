# AeroState

AeroState is a Home Assistant custom integration that exposes supported IR air conditioners as native climate entities.

Release: v1.1.5

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

## Supported Runtime Paths

- Broadlink remote entities with existing Broadlink packs.
- LG Tuya local IR using the existing AKB75415308 local pack.
- Daikin Tuya local IR using a manually tested and confirmed local code-set pack.
- No Tuya Cloud calls during normal local climate control.

## Verified LG Production Scope

- Active Broadlink production pack: lg.pc09sq_nsj.protocol.v1
- Model: LG PC09SQ NSJ
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

For Daikin BRC4M150W / FXAQ63PVE6 ACs using a Tuya IR blaster, import code-set
packs once, test packs one command at a time, then confirm the working pack.
Runtime control uses only that confirmed local pack.

### Daikin Code-Set UI

The Tuya IR Setup screen shows the number of imported Smart Life-style Daikin
sets installed locally. To import sets directly from Home Assistant:

1. Select **Daikin** as the Tuya AC brand.
2. Select **Import Daikin code sets from Tuya once** under **Daikin code-set setup**.
3. Select the local Tuya IR remote entity and submit.
4. Enter the Tuya OpenAPI endpoint, Access ID, Access Secret, and IR blaster device ID.
5. Select one imported Daikin set and one command such as `power_on`.
6. Test that single command and confirm the pack only after the AC responds.

Tuya command-pack selectors show only packs matching the selected AC brand.
The Daikin one-time import choice is hidden during LG setup.

Credentials are used only during the import request and are not saved in the
integration config entry. Valid generated packs are written under
`custom_components/aerostate/packs/tuya/daikin/`. The repository does not
contain fabricated Daikin payloads. Tuya sets that do not contain the required
local commands are skipped.

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
- Tuya Daikin code-library setup: docs/TUYA_DAIKIN_CODE_LIBRARY_SETUP.md
- Changelog: CHANGELOG.md
- Release notes: RELEASE_NOTES.md
