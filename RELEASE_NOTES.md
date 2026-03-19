# Release Notes

## AeroState v0.1.0-rc1

AeroState v0.1.0-rc1 is the first installer-facing release candidate.

### Highlights
- Broadlink-only transport path via `remote.send_command` with `b64:` payload formatting.
- UI-first setup and reconfiguration flow with duplicate prevention safeguards.
- Verified LG cool-only pack (`lg.pc09sq_nsj.v1`) with explicit no-swing limitation.
- Safe onboarding/self-test validation and diagnostics visibility.

### Known limitations
- Only Broadlink is supported.
- Only verified cool-only LG pack is included.
- Swing controls are intentionally unavailable until real payloads are verified.
- Verified packs expose only payloads proven to work in real testing.
