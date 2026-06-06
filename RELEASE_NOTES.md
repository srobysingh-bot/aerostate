# Release Notes

## AeroState v1.1.0

This release adds isolated local Daikin Tuya code-set support while preserving
existing LG Tuya and Broadlink behavior.

### Added

- One-time Tuya Cloud importer for local Daikin code-set generation.
- Isolated local Daikin pack loader with payload and required-command validation.
- `aerostate.test_tuya_pack` for one-command manual pack testing.
- `aerostate.confirm_tuya_pack` for selecting the only Daikin runtime pack.
- Offline Daikin runtime control with OFF-to-ON power sequencing.

### Safety

- No automatic pack cycling.
- No Tuya Cloud calls during normal climate control.
- Test commands do not update climate assumed state.
- Daikin runtime remains isolated from LG Tuya and Broadlink providers.
- Full payloads are not logged.

### Verification

- Existing LG Tuya regression coverage passes.
- Existing Broadlink regression coverage passes.
- Daikin power-off sends exactly once.
- Full test suite passes.
