# Changelog

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
