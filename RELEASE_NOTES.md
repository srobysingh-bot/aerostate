# Release Notes

## AeroState v1.0.0

This is the first production-ready AeroState release for the verified LG protocol scope.

### Production-Verified Behavior

- Config flow and options flow are stable for normal setup and maintenance.
- Active protocol pack: lg.pc09sq_nsj.protocol.v1.
- Verified HVAC modes: auto, cool, heat, dry, fan_only.
- Verified temperature range: 16-30 C.
- Verified fan levels: auto, low, mid, high, highest.
- Verified vertical swing support.
- Verified horizontal swing in the currently supported form (off/on).
- Command throughput remains smooth with debounce + latest-state-wins + serialized sending.

### Hardening Included

- Finalized pack truth metadata (verified flags, physically verified modes, mode status).
- Diagnostics now include a concise support summary for fast triage.
- Config flow handles missing selected packs safely.
- Options flow rejects invalid pack reconfiguration states safely.

### Intentional Limitations

- Jet/Turbo is disabled until model-specific protocol ON/OFF frames are verified.
- Advanced horizontal swing positions are intentionally hidden until verified for this model.
- Broadlink remains the only supported transport backend.
