# Release Notes

## AeroState v1.1.1

This patch adds the missing Home Assistant manual-test UI for imported local
Daikin Tuya code sets.

### Added

- Imported Daikin set count on the Tuya IR Setup screen.
- Dedicated set, command, and Test/Confirm selectors.
- Automatic transition into manual testing when an imported Daikin set is selected.

### Safety

- Confirmation is blocked until the selected set has been tested.
- Each test sends one command only, with a two-second cooldown.
- No automatic pack cycling or runtime Tuya Cloud calls.

### Verification

- Manual-test UI flow and confirmation behavior are covered by tests.
- Existing LG Tuya and Broadlink regressions continue to pass.
