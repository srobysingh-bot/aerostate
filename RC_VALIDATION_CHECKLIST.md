# AeroState RC Validation Checklist (Real HA)

Use this checklist in a clean Home Assistant test instance for v0.1.0-rc1.

## Environment
- Home Assistant version:
- Host type (OS/Supervised/Core):
- Broadlink integration status:
- Test AC model:
- AeroState build/tag: v0.1.0-rc1

## Installer Flow
1. Install integration (HACS/manual)
   - Result: PASS/FAIL
   - Notes:
2. Add via config flow
   - Result: PASS/FAIL
   - Notes:
3. Select Broadlink entity
   - Result: PASS/FAIL
   - Notes:
4. Select verified LG pack
   - Result: PASS/FAIL
   - Notes:
5. Link temperature/humidity sensors
   - Result: PASS/FAIL
   - Notes:
6. Run onboarding validation
   - Result: PASS/FAIL
   - Notes:
7. Create thermostat card
   - Result: PASS/FAIL
   - Notes:
8. Run aerostate.run_self_test
   - Result: PASS/FAIL
   - Notes:
9. Change pack/controller in options flow
   - Result: PASS/FAIL
   - Notes:

## Error Capture
- UI errors (copy exact text):
- Home Assistant logs/exceptions:
- Repair issues raised:
- Diagnostics snapshot reviewed: YES/NO

## Outcome
- Release candidate status: GO / NO-GO
- Required fixes before pilot:
