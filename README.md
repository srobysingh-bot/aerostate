# AeroState

AeroState is a Home Assistant custom integration that exposes supported IR air conditioners as standard climate entities.

Release candidate: **v0.1.0-pilot** (🎉 [Read Pilot Release Notes](PILOT_RELEASE_NOTES.md))

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Add the AeroState repository as a custom integration source: `https://github.com/srobysingh-bot/aerostate`
3. Install AeroState.
4. Restart Home Assistant.
5. Add AeroState from Devices & Services.

### Manual install

1. Copy the `custom_components/aerostate` folder into your Home Assistant config directory under `custom_components/`.
2. Restart Home Assistant.
3. Add AeroState from Devices & Services.

## Current Support

- Transport backend: Broadlink remote entities only
- Setup method: UI config flow only (no YAML)
- Current built-in pack status:
  - LG `lg.pc09sq_nsj.v1`
  - ✅ **Verified cool-only** command matrix
  - Fan modes: auto, low, mid, high
  - Temperatures: 18-30°C (1°C steps)
- Swing controls are intentionally not exposed until verified payloads are available.

## Quick Start

1. Add the integration from Home Assistant UI.
2. Select your Broadlink remote entity.
3. Select brand and model pack (currently LG verified only).
4. Optionally link room temperature/humidity/power sensors.
5. Run validation during onboarding (optional, for real AC testing).
6. Add a thermostat card for the AeroState climate entity.
7. Test OFF/COOL/fan modes/temperatures with your AC.

## Pilot Testing

This is a **pilot release** for real-world testing. See [PILOT_RELEASE_NOTES.md](PILOT_RELEASE_NOTES.md) for:
- Installation walkthrough  
- Validation checklist  
- Troubleshooting guide  
- Feature roadmap  
- How to report bugs  

**TL;DR:** Install via HACS, test with LG cool-only AC + Broadlink remote, run `aerostate.run_self_test`, report any issues.

## Pack Expansion Workflow

AeroState packs are expanded **only with verified, tested payloads**. See [PACK_AUTHORING_GUIDE.md](PACK_AUTHORING_GUIDE.md) for:

### For Users: Contributing a New AC Pack

1. Have real AC hardware + Broadlink remote
2. Capture IR payloads for all modes/fans/temps you want to support
3. Use pack authoring tools to create pack JSON
4. Test locally in Home Assistant  
5. Submit PR with pack + testing documentation

### For Developers: Expanding Existing Packs

1. Use `packs/pack_authoring.py` tools:
   ```python
   from custom_components.aerostate.packs.pack_authoring import (
       suggest_pack_expansion,
       validate_matrix_structure,
       describe_pack_expansion_readiness,
   )
   
   # Expand cool pack with heat payloads
   expanded = suggest_pack_expansion(
       current_pack=lg_cool_pack,
       new_hvac_mode="heat",
       template_mode="cool",
   )
   
   # Validate completeness
   reports = validate_matrix_structure(...)
   ```

2. Use `packs/pack_import.py` to convert existing matrices:
   ```python
   from custom_components.aerostate.packs.pack_import import (
       convert_flat_matrix_to_pack,  # For {cool_18_auto: payload} format
       convert_csv_matrix_to_pack,   # For CSV exported matrices
       validate_imported_pack,
   )
   ```

3. For detailed pack authoring workflows, see [PACK_AUTHORING_GUIDE.md](PACK_AUTHORING_GUIDE.md)

## Self-Test Service

Service: `aerostate.run_self_test`

- Use `entry_id` or `entity_id` to target a configured AC.
- `profile: basic` runs the minimum safe validation set (OFF state only).
- `profile: full` runs additional states (OFF + test COOL + test fan).
- Results published as `aerostate_self_test_result` event in Home Assistant

```yaml
service: aerostate.run_self_test
data:
  entity_id: climate.aerostate_lg_pc09sq_nsj
  profile: full
```

## Installer Checklist

Quick validation checklist:

1. ✅ Add AeroState integration.
2. ✅ Select Broadlink remote entity.
3. ✅ Select LG PC09SQ NSJ verified pack.
4. ✅ Link temperature/humidity sensors (optional).
5. ✅ Run onboarding validation.
6. ✅ Add thermostat card to dashboard.
7. ✅ Test thermostat card:
   - Set OFF → AC stops
   - Set COOL → AC cools
   - Change fan: Auto → Low → Mid → High
   - Change temp: 18 → 30 (verify AC adjusts)
8. ✅ Run `aerostate.run_self_test` (profile: full)

For formal tracking, use [RC_VALIDATION_CHECKLIST.md](RC_VALIDATION_CHECKLIST.md).

## Limitations

- **Verified LG pack** is currently cool-only. Heat/Dry/FanOnly coming in Phase 11+ after real AC testing.
- **No swing payloads** are included in any pack until verified patterns exist.
- **Broadlink is the only supported transport** in this release.
- **Single AC per config entry**: One Broadlink remote + one AC model per entry.
- **No automation support** yet (trigger/condition/action for climate states coming later).

## Troubleshooting

### "Remote entity not available"
- Ensure Broadlink integration is set up in Home Assistant
- Verify `remote.living_room_ac` (or similar) is listed under Settings > Devices & Services
- Check Developer Tools > States for `remote.xxx` with state `on` or `off` (not `unavailable`)

### "Validation failed: no response"
- Ensure AC is powered ON
- Point Broadlink remote directly at AC before running validation
- Check Broadlink has clear line-of-sight to AC
- Try manual Broadlink test first: Settings > Devices > Broadlink > Send Command

### "Climate entity not appearing"  
- Check Home Assistant logs (Settings > System > Logs) for `aerostate` errors
- Verify config entry exists (Settings > Devices & Services > Aerostate)
- If entity exists but not visible: add manually to dashboard (entity: `climate.aerostate_<model>_<id>`)

### "AC beeps but won't cool"
- Verify correct Broadlink remote selected (try manual send with Broadlink test)
- Confirm payload format correct (`b64:` prefix for Broadlink)
- Re-run `aerostate.run_self_test` and check diagnostics

For more detailed troubleshooting, see [PILOT_RELEASE_NOTES.md](PILOT_RELEASE_NOTES.md#troubleshooting).

## Verified Pack Policy

- Verified packs (**`verified: true`**) only expose features with proven, working payloads
- Unverified/partial packs (**`verified: false`**) are available for beta testing
- Unsupported features (e.g., swing) are **not exposed or simulated**
- All new packs start as `verified: false` until community testing validates them

## Pack Lifecycle

Model packs carry lifecycle metadata:

- **`pack_version`**: integer version for update/migration (incremented when modes added)
- **`verified`**: `true` only after real AC testing; `false` for beta/imported packs
- **`notes`**: Human-readable limitations and status (e.g., "Verified cool-only. Heat mode under expansion.")

Example notes evolution:
- v1 (initial): `"Verified cool-only. No swing payloads."`
- v2 (after heat expansion): `"Verified cool and heat modes (18-30°C, all fan modes). No swing yet."`

## Contributing

See [PACK_AUTHORING_GUIDE.md](PACK_AUTHORING_GUIDE.md) for detailed pack contribution workflows.

### Quick PR Checklist for New Packs

1. Real AC hardware tested ✓
2. All payloads captured and verified ✓
3. Pack JSON created using authoring tools ✓
4. Local validation passes: `pytest tests/ -v -k pack` ✓
5. Tested in real Home Assistant instance ✓
6. PR includes: pack JSON + AC model + testing notes ✓

## Roadmap

- **Phase 10 (current)**: Pilot validation + pack authoring tools
- **Phase 11**: Heat mode expansion (after LG pilot validation)
- **Phase 12**: Dry + Fan-Only modes
- **Phase 13+**: Swing support, additional brands, automation triggers

See [PILOT_RELEASE_NOTES.md](PILOT_RELEASE_NOTES.md#pack-expansion-roadmap) for full roadmap.

## Support & Issues

- **Questions:** See [PILOT_RELEASE_NOTES.md](PILOT_RELEASE_NOTES.md#troubleshooting)  
- **Pack authoring:** See [PACK_AUTHORING_GUIDE.md](PACK_AUTHORING_GUIDE.md)  
- **Bug reports:** Open issue at https://github.com/srobysingh-bot/aerostate/issues  
- **Feature requests:** Use GitHub Discussions or open issue with `enhancement` label

## Technical Details

### Architecture

- **Platform:** Home Assistant 2024.1.0+  
- **Framework:** Async climate entity with config/options flows
- **Pack engine:** Table-based command resolution (state dict → payload lookup)
- **Transport:** Broadlink `remote.send_command` service (base64 IR codes)
- **Validation:** JSON schema + HomeAssistant entity checks
- **Tests:** 50+ unit/integration tests, full linting

### Project Structure

```
custom_components/aerostate/
├── __init__.py              # Entry point, service registration
├── climate.py               # Climate entity
├── config_flow.py           # 7-step setup wizard
├── options_flow.py          # Reconfiguration flow
├── flow_helpers.py          # Shared config logic
├── diagnostics.py           # Device diagnostics
├── validation.py            # Validation state builder
├── repairs.py               # Repairs UI (optional)
├── packs/
│   ├── schema.py            # ModelPack dataclass
│   ├── loader.py            # JSON validation
│   ├── registry.py          # Pack singleton registry
│   ├── pack_authoring.py    # ✨ Pack expansion tools
│   ├── pack_import.py       # ✨ Import/conversion tools
│   ├── coverage.py          # Coverage reporting
│   └── builtin/lg/
│       └── pc09sq_nsj_v1.json  # Verified LG cool-only pack
├── engines/
│   └── table_engine.py      # Table-based command engine
└── providers/
    └── broadlink.py         # Broadlink transport

tests/
├── test_pack_authoring.py   # ✨ Pack authoring tool tests
├── test_pack_import.py      # ✨ Pack import tool tests
├── test_climate_*.py        # Climate entity tests
├── test_config_flow_*.py    # Config flow tests
├── test_options_flow_*.py   # Options flow tests
└── ... (10+ other test files)
```

## FAQ

**Q: Can I use AeroState with non-Broadlink IR remotes?**  
A: Not yet. Phase 13+ will add additional transport backends (GPIO IR blasters, etc.).

**Q: How do I add support for Daikin / Mitsubishi / other brands?**  
A: See [PACK_AUTHORING_GUIDE.md](PACK_AUTHORING_GUIDE.md). You need real AC hardware + Broadlink remote + payloads captured for your model.

**Q: Can I add swing mode?**  
A: Only for AC models with verified swing payloads. For LG pack, coming in Phase 12+ after we have tested swing codes.

**Q: Will this work offline?**  
A: Yes. All IR codes are local. No cloud dependency or API calls.

**Q: Can I automate with AeroState climate entities?**  
A: Currently, only manual thermostat control. Automation triggers coming in Phase 13+.

---

**Ready to pilot?** Install via HACS and see [PILOT_RELEASE_NOTES.md](PILOT_RELEASE_NOTES.md). Happy cooling! 🎉

This allows stable installer behavior today while preparing future pack updates.
