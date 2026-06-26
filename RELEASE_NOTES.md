# Release Notes

## AeroState v1.1.4

This patch adds the Daikin BRC4M150W / FXAQ63PVE6 local Tuya workflow.

### Added

- Target pack generation for `daikin_brc4m150w_fxaq63pve6_localtuya_rc_v1`.
- Tuya import priority for BRC4M150W, BRC4M150, FXAQ63PVE6, FXAQ, and commercial Daikin families.
- Physical remote capture JSON fallback for building the same local Tuya raw pack.

### Safety

- BRC4C158 is no longer presented as the final pack for FXAQ63PVE6.
- Target packs require localtuya_rc raw payloads and reject Broadlink b64.
- Runtime stays local/offline after import or capture.

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
