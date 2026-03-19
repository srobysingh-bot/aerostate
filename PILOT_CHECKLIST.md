# AeroState Pilot Checklist (Client 1)

Version target: v0.1.0-rc1

## Pre-checks
- Confirm client AC is supported by verified LG cool-only pack.
- Confirm Broadlink remote entity exists and can send IR commands.
- Confirm no expectation of swing support for this pilot.

## Install
1. Install AeroState.
2. Complete config flow with Broadlink + verified LG pack.
3. Link temperature/humidity sensors if available.
4. Run onboarding validation and self-test (basic profile).

## Acceptance
- Climate card appears and is controllable.
- HVAC modes include OFF + COOL only.
- Fan modes match pack (auto/low/mid/high).
- No swing controls exposed.
- Diagnostics show pack verified=true and expected notes.

## Support Notes
- If AC beeps but does not change state, review IR path and remote selection.
- Do not enable unsupported features.
- Keep current pack marked verified cool-only until real swing payloads are verified.
