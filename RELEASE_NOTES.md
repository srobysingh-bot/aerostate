# Release Notes

## AeroState v1.1.3

This patch makes Tuya local pack selection brand-aware.

### Fixed

- New Tuya setups select the AC brand before choosing a command pack.
- Daikin setup lists only Daikin packs.
- LG setup lists only LG packs.
- Options flow lists only packs matching the existing entry brand.

### Safety

- Daikin import is available only during Daikin setup.
- Cross-brand pack submissions are rejected.
- Imported Daikin packs appear only while their local files exist.

### Verification

- Brand-filtered setup and Options selectors are covered by tests.
- Existing LG Tuya runtime and Broadlink regressions continue to pass.
