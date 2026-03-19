# AeroState

AeroState is a Home Assistant custom integration that exposes supported IR air conditioners as standard climate entities.

Release candidate: v0.1.0-rc1

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Add the AeroState repository as a custom integration source.
3. Install AeroState.
4. Restart Home Assistant.
5. Add AeroState from Devices & Services.

### Manual install

1. Copy the `custom_components/aerostate` folder into your Home Assistant config directory under `custom_components/`.
2. Restart Home Assistant.
3. Add AeroState from Devices & Services.

## Current Support

- Transport backend: Broadlink remote entities only
- Setup method: UI config flow only (no YAML)
- Current built-in pack status:
  - LG `lg.pc09sq_nsj.v1`
  - Verified cool-only command matrix
  - Fan modes: auto, low, mid, high
  - Temperatures: 18-30
- Swing controls are intentionally not exposed until verified payloads are available.

## Installer Notes

1. Add the integration from Home Assistant UI.
2. Select a Broadlink remote entity.
3. Select brand and model pack.
4. Optionally link room temperature/humidity/power sensors.
5. Run validation during onboarding or later via the self-test service.

## End-to-End Installer Checklist

1. Add AeroState integration.
2. Select Broadlink remote.
3. Select LG verified pack.
4. Link temperature/humidity sensors.
5. Run onboarding validation.
6. Add a thermostat card for the AeroState climate entity.
7. Run `aerostate.run_self_test` (basic profile first).

For formal run tracking, use `RC_VALIDATION_CHECKLIST.md`.

## Self-Test Service

Service: `aerostate.run_self_test`

- Use `entry_id` or `entity_id` to target a configured AC.
- `profile: basic` runs the minimum safe validation set.
- `profile: full` runs one additional supported validation state.

## Limitations

- Verified LG pack is currently cool-only.
- No swing payloads are included in the verified pack.
- Broadlink is the only supported transport in this release.

## Troubleshooting

- Beep but no physical change:
  - Verify the correct Broadlink remote is selected.
  - Confirm line-of-sight and IR reach.
  - Re-run self-test and review diagnostics coverage gaps.
- Unsupported pack states:
  - AeroState intentionally rejects unsupported mode/fan/temp requests.
  - Use only states exposed by the entity for the selected pack.
- Broadlink unavailable:
  - Confirm `remote.send_command` service availability.
  - Ensure the selected Broadlink entity is online.
- Linked sensors unavailable:
  - Check entity IDs and sensor availability states.
  - Remove/relink sensors in options flow if entities changed.

## Verified Pack Policy

- Verified packs only expose features with proven, working payloads.
- Unsupported features (such as swing for current LG pack) are not exposed or simulated.

## Future Notes

- Example screenshots and expanded usage walkthroughs can be added in a later documentation pass.

## Pack Lifecycle

Model packs carry lifecycle metadata:

- `pack_version`: integer version for update/migration readiness
- `verified`: indicates production verification state
- `notes`: limitations or operational notes

This allows stable installer behavior today while preparing future pack updates.
