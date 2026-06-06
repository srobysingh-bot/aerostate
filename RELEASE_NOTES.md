# Release Notes

## AeroState v1.1.2

This patch adds the missing one-time Daikin Tuya import choice directly to the
Home Assistant setup UI.

### Added

- **Import Daikin code sets from Tuya once** choice in Tuya IR Setup.
- Temporary Tuya credential form; credentials are not saved.
- Persistent imported packs under `/config/aerostate_tuya_daikin_codes/`.
- Automatic transition into the manual Test/Confirm screen after a successful import.

### Safety

- Incomplete or incompatible Tuya sets are skipped.
- Confirmation remains blocked until the selected set has been tested.
- No automatic pack cycling and no runtime Tuya Cloud calls.

### Verification

- One-time import persistence and credential isolation are covered by tests.
- Existing LG Tuya and Broadlink regressions continue to pass.
