# AeroState Pilot Release Notes (v0.1.0-pilot)

**Release Date:** March 19, 2026  
**Status:** Release Candidate for First Client Pilot  
**Target Users:** Single real Home Assistant instance with compatible AC unit

---

## What is v0.1.0-pilot?

This is the **first release candidate** of AeroState ready for real-world testing. It includes:
- ✅ Complete config flow UI (7-step wizard)
- ✅ Climate entity with capability-based feature exposure
- ✅ Single verified pack (LG cool-only)
- ✅ Broadlink transport support (base64 payloads)
- ✅ Self-test service for diagnostics
- ✅ 50+ automated tests (unit + integration)
- ✅ Pack authoring tooling for future expansion

---

## What's Tested

### Integration Flow (Manual)
- [ ] HACS discovery and installation
- [ ] Config flow: remote selection → brand → model → sensor linking
- [ ] Validation step (optional, for real AC testing)
- [ ] Climate entity creation in Home Assistant
- [ ] Thermostat card display and interaction

### LG Cool-Only Pack (Verified)
- ✅ Automatic unit: off + cool mode, auto/low/mid/high fan, 18–30°C
- ✅ Table engine command resolution
- ✅ Broadlink b64: payload format
- ⚠️ **Real AC testing:** Not yet validated on actual hardware

### Code Quality
- ✅ 50 unit/integration tests passing
- ✅ linting: ruff all rules passing
- ✅ Type hints: partial coverage
- ⚠️ **Edge cases:** Limited real-world error handling

---

## Known Limitations

### Supported Features (Currently)
- **HVAC Modes:** OFF, COOL only
- **Fan Modes:** Auto, Low, Mid, High
- **Temperature:** 18–30°C (1°C steps)
- **Transport:** Broadlink remote entity (no other protocols yet)
- **Swing:** Not supported (no verified payloads)
- **Presets:** Not supported

### Not Included in Pilot
- Heat, Dry, or Fan-Only modes (planned after AC validation)
- Swing payloads (requires verified patterns from real hardware)
- Multiple pack support in config flow (coming Post-pilot)
- Swing controls in thermostat card
- Humidity sensing or presets
- Non-Broadlink transports (e.g., direct IR blasters)

### Pilot Constraints
- **One pack only:** LG PC09SQ NSJ (verified cool-only)
- **One AC unit:** Must be LG cool-only compatible
- **Manual operation:** No automation/automations board items
- **No cloud:** Fully local, no remote validation

---

## How to Pilot This Release

### Prerequisites
- Home Assistant 2024.1.0+
- HACS installed and working
- One Broadlink remote entity set up (e.g., RM4 Pro, RM Mini 3, etc.)
- One compatible LG AC unit (cool-only, PC09SQ or NSJ variant)

### Installation Steps
1. In HACS → Custom Repositories, add:  
   `https://github.com/srobysingh-bot/aerostate`
2. Select **Aerostate** and click **Install**
3. Restart Home Assistant
4. Go to **Settings > Devices & Services > Create Automation > AeroState**
5. Follow the 7-step config flow

### Validation Flow
1. Select your Broadlink remote entity  
   *(UI will verify entity availability)*
2. Select Brand: **LG**  
3. Select Model: **PC09SQ NSJ**  
4. Link optional temperature sensor (optional step)  
5. Test Commands (optional):
   - Select test profile (Basic / Full)
   - AeroState sends test power + cool commands
   - Verify AC responds (LED lights, compressor cycles)
6. Add Thermostat Card and test physically:
   - Set mode OFF → Check AC stops
   - Set mode COOL → Check AC cools
   - Adjust fan: Auto → Low → Mid → High → Check airflow cycles
   - Adjust temp: 18 → 30 → Check AC efficiency change

### Report Results
After piloting, run **Services > aerostate.run_self_test** (profile: Full) and report:
- ✅ All UI steps completed without errors
- ✅ Thermostat card shows correct capabilities
- ✅ AC responds to all OFF/COOL/fan/temp commands
- ⚠️ Any unexpected behavior or errors

**Or send issues to:**  
srobysingh-bot@example.com or open GitHub issue at:  
https://github.com/srobysingh-bot/aerostate/issues

---

## Pack Expansion Roadmap

After pilot validation, the next packs will be added **only with real verified payloads:**

### Phase 11: Heat Mode (Post-Pilot)
- Collect verified HEAT mode payloads from pilot AC
- Add `heat` branch to LG pack
- Expand `capabilities.hvac_modes` to include `["cool", "heat"]`
- Re-verify and tag as v0.1.1
- **Requires:** Real AC testing with heat mode

### Phase 12: Additional Modes (Dry, Fan-Only)
- Follow same verified payloads approach
- Expand fan modes if real hardware supports additional levels
- Add swing support **only after** verified payloads exist

### Future Packs (Post-Phase-12)
- Daikin, Hitachi, Mitsubishi, other popular brands
- Each with same verified-only discipline
- Community contributions welcome (must include real AC testing)

---

## Troubleshooting

### "Remote entity not available"
- ✅ Ensure Broadlink integration is loaded in Home Assistant
- ✅ Verify `remote.living_room_ac` (or similar) is listed under Settings > Devices & Services > Broadlink Remote
- ✅ Check that remote entity state is not "unavailable" in Developer Tools > States

### "Validation failed: no response"
- ✅ Ensure AC is powered ON
- ✅ Point Broadlink remote at AC unit before running test
- ✅ Check that Broadlink has a clear line-of-sight to AC
- ✅ Run Broadlink test directly: **Broadlink > Send Command > Test Power Off**
	- If that fails, Broadlink hardware is misconfigured (restart integration)
	- If that works, AeroState payload might be incorrect (report bug)

### "Climate entity not appearing"
- ✅ Check Home Assistant logs: **Settings > System > Logs**
- ✅ Look for errors from `custom_components.aerostate` domain
- ✅ Ensure config entry was created (Settings > Devices & Services > AeroState)
- ✅ If entity exists but not visible: add manually to dashboard
	- Card type: **Thermostat**
	- Entity: `climate .aerostate_<model><instance_id>`

### "AC not responding to commands"
1. Try manual Broadlink test first (see "no response" above)
2. If manual Broadlink works but AeroState doesn't:
   - Check **Services > aerostate.run_self_test** debug output
   - Report error payload + Broadlink model to GitHub issues

---

## Support & Feedback

### Reporting Issues
1. Run **Services > aerostate.run_self_test** (profile: Full)
2. Capture Home Assistant logs (Settings > System > Logs)
3. Open issue at: https://github.com/srobysingh-bot/aerostate/issues
4. Include:
   - AC model + Broadlink remote model
   - Config entry JSON (Settings > Devices > AeroState > Configuration)
   - Full self-test output
   - Relevant logs

### Pilot Success Criteria
- ✅ 1 pilot user successfully installs via HACS
- ✅ Climate entity created and visible in Home Assistant
- ✅ OFF/COOL/fan/temp commands work on real AC
- ✅ No major UI crashes or silent failures
- **Then:** Move to Phase 11 (heat mode expansion)

---

## Technical Details

### Pack Format
- **Engine:** Table-based (state dict → command lookup)
- **Transport:** Broadlink base64 (b64: prefix)
- **Validation:** JSON schema with HomeAssistant entity checks
- **Versioning:** manifest.json v0.1.0-pilot, pack_version = 1

### Code Metrics (v0.1.0-pilot)
- **Test Coverage:** 50 passing, 4 skipped (HA integration tests)
- **Linting:** 100% pass (ruff E/F/W/I)
- **Custom Integration Size:** 28 KB (code) + 12 KB (packs)
- **Dependencies:** homeassistant ≥ 2024.1.0, voluptuous

### Files & Structure
```
custom_components/aerostate/
├── __init__.py (entry point, service registration)
├── climate.py (climate entity)
├── config_flow.py (7-step wizard)
├── options_flow.py (entry reconfiguration)
├── flow_helpers.py (shared logic)
├── diagnostics.py (device diagnostic data)
├── validation.py (command matrix inspection)
├── repairs.py (optional repairs UI)
├── packs/
│   ├── schema.py (ModelPack dataclass)
│   ├── loader.py (JSON validation)
│   ├── registry.py (singleton registry)
│   ├── pack_authoring.py (✨ NEW: authoring tools)
│   ├── pack_import.py (✨ NEW: import/conversion)
│   └── builtin/lg/pc09sq_nsj_v1.json (verified LG cool-only)
├── engines/
│   └── table_engine.py (command resolution)
└── providers/
    └── broadlink.py (transport implementation)

tests/ (50 tests)
├── test_climate_capabilities.py
├── test_config_flow_*.py
├── test_options_flow_*.py
├── test_pack_authoring.py (✨ NEW)
├── test_pack_import.py (✨ NEW)
├── test_*.py (10+ others)
└── ...
```

---

## Next Steps

### Immediate (Before Pilot)
1. ✅ Code freeze: No new features until pilot validation complete
2. ✅ GitHub push: All code published for transparency
3. ⏳ Pilot testing: Single real user with LG + Broadlink
4. ⏳ Issue collection: Document any bugs/UX problems

### Post-Pilot (Success Path)
1. Fix any pilot-reported bugs (v0.1.0-patch)
2. Collect real HEAT mode payloads from pilot AC
3. Expand LG pack with heat mode (v0.1.1)
4. Release v0.1.1 with heat support
5. Open packs for community submissions (verified payloads only)

### Post-Pilot (Go-No-Go)
- **GO:** No critical issues, AC works reliably → Phase 11 (heat)
- **NO-GO:** Major issues found → Return to Phase 9 (fix architecturally)

---

**Ready to pilot?** Install via HACS and report back. Good luck! 🎉
