# Changelog

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
