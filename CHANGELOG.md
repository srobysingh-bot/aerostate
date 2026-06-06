# Changelog

## 1.1.3 - 2026-06-06

### Fixed
- Tuya setup now asks for the AC brand before showing command packs.
- Daikin setup shows only Daikin-compatible local packs.
- LG setup shows only LG-compatible local packs.
- Options flow filters Tuya packs using the configured entry brand.

### Safety
- The Daikin one-time import action is shown only for Daikin setup.
- Cross-brand Tuya pack submissions are rejected.
- Stale imported Daikin registry entries are hidden when their local pack file no longer exists.

## 1.1.2 - 2026-06-06

### Added
- One-time Daikin Tuya code-set import flow inside Home Assistant.
- Temporary credential form that does not store Tuya credentials in the config entry.
- Persistent imported-pack storage under `/config/aerostate_tuya_daikin_codes/`.

### Changed
- Imported user packs are discovered during setup, options, testing, services, and runtime.
- The Daikin import choice appears before the command-pack selector in Tuya IR Setup.

### Safety
- Only complete validated local packs are saved; incomplete Tuya sets are skipped.
- Runtime remains local and uses only the manually tested and confirmed pack.

## 1.1.1 - 2026-06-06

### Added
- Dedicated Home Assistant config-flow screen for manually testing imported Daikin Tuya code sets.
- UI selectors for one local set, one command, and either Test or Confirm.
- Visible imported-set count in the Tuya setup screen.

### Safety
- Confirmation is blocked until the selected set has been manually tested.
- Testing sends exactly one selected command and retains the two-second cooldown.
- AeroState never automatically cycles through all installed Daikin sets.

## 1.1.0 - 2026-06-06

### Added
- Isolated local Daikin Tuya code-set loader and one-time Tuya Cloud importer.
- Safe one-command Daikin pack testing and explicit confirmed-pack selection services.
- Offline Daikin runtime control using only the confirmed local pack.
- Daikin runtime, loader, service isolation, and exact-once power-off regression tests.

### Changed
- Tuya pack registration now loads bundled and generated local packs explicitly.
- Daikin local runtime requires a confirmed pack and reports a repair issue when missing.

### Unchanged
- Existing LG Tuya packs and runtime behavior.
- Existing Broadlink provider, packs, and runtime behavior.

## 1.0.1 - 2026-05-31

### Fixed
- Tuya LG AKB75415308 stateful raw OFF -> ON now sends `power_on`, waits briefly, then sends the combined mode/temperature/fan command.
- Tuya duplicate-skip logic now resends ON when linked or remembered power feedback says the AC is still off.

## 1.0.0 - 2026-03-20

First production-ready AeroState release for the verified LG protocol scope.

### Added
- Production truth metadata for lg.pc09sq_nsj.protocol.v1.
- Diagnostics support summary with selected pack, engine type, protocol path status, verified modes, swing status, fan modes, temperature range, linked sensors, and limitations.
- Config flow hardening for missing selected pack during validation/confirm.
- Options flow hardening for invalid model-pack reconfiguration.
- Regression tests covering protocol pack truth, diagnostics summary, and flow hardening paths.

### Changed
- Active protocol pack marked verified with physically verified HVAC modes.
- Verified temperature range finalized to 16-30 C and fan set finalized to 5 levels (auto, low, mid, high, highest).
- Manifest version updated to 1.0.0.
- README updated for production setup, support scope, and troubleshooting.

### Intentionally Unchanged
- Jet/Turbo remains disabled pending model-specific verified ON/OFF frames.
- Advanced horizontal swing positions remain hidden pending verified mappings.
- Latest-state-wins command pipeline, debounce behavior, and serialized Broadlink sending remain unchanged.

## 0.1.0-pilot - 2026-03-19

**Pilot release for real-world testing.** First production-targeting release with pack authoring tools.

### Added
- ✨ **Pack authoring tools:** `pack_authoring.py` for validating/expanding packs incrementally.
- ✨ **Pack import utilities:** `pack_import.py` for converting known matrices (flat/CSV) to AeroState format.
- 🧪 25 new tests for pack tools (50 total in suite).
- `PILOT_RELEASE_NOTES.md` with installation walkthrough, validation checklist, troubleshooting, and roadmap.
- `PACK_AUTHORING_GUIDE.md` with workflows for expanding packs and contributing new AC models.
- Enhanced README with pack expansion workflow and contributor guidance.

### Changed
- Version: 0.1.0-rc1 → 0.1.0-pilot (Phase 10 readiness)
- README: Added pack expansion, roadmap, FAQ, contributing sections
- Manifest: Repository URL included for HACS discovery

### Fixed
- Import ordering in `__init__.py` (ruff compliance)
- Pack registry metadata preservation

### Status
- ✅ 50 tests passing, 4 skipped (HA integration tests)
- ✅ Linting: 100% pass (ruff E/F/W/I)
- ✅ Ready for real-world pilot with LG cool-only AC + Broadlink

## 0.1.0-rc1 - 2026-03-19

First installer-facing AeroState release candidate.

### Added
- UI config flow and options flow for Broadlink-backed AeroState entries.
- Verified LG pack `lg.pc09sq_nsj.v1` (cool-only, no swing payloads).
- Self-test service: `aerostate.run_self_test`.
- Diagnostics and repair issue reporting for pack/runtime validation.
- Unit test coverage for config/options duplicate prevention, pack loader/coverage, table engine, provider formatting, diagnostics output, and climate capability mapping.

### Notes
- Broadlink transport only in this release.
- Swing support remains disabled until verified payloads are available.
