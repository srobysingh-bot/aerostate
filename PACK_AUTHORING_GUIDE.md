# Pack Authoring Guide

**For:** Developers expanding AeroState packs with new modes and capabilities  
**Updated:** March 19, 2026  
**Status:** Phase 10+ guidance

---

## Overview

AeroState packs define **command matrices** that map Home Assistant climate states (HVAC mode, fan mode, temperature) to Broadlink IR payloads. This guide explains how to:
1. Create new packs from known command matrices
2. Expand existing packs with new modes
3. Validate pack completeness
4. Convert various matrix formats to AeroState format

---

## Pack Structure Primer

### What Is a Pack?

A pack is a JSON file describing an AC unit's command patterns:

```json
{
  "id": "lg.pc09sq_nsj.v1",
  "brand": "LG",
  "models": ["PC09SQ NSJ"],
  "transport": "broadlink_base64",
  "min_temperature": 18,
  "max_temperature": 30,
  "temperature_step": 1,
  "verified": true,
  "notes": "Verified cool-only pack. No swing payloads.",
  "capabilities": {
    "hvac_modes": ["cool"],
    "fan_modes": ["auto", "low", "mid", "high"],
    "swing_vertical_modes": [],
    "swing_horizontal_modes": []
  },
  "commands": {
    "off": "JgCUAP2/BgAeFh+/A...",
    "cool": {
      "auto": {
        "18": "JgCUAP2/BgAeFh+/A...",
        "19": "JgCUAP2/BgAeFh+/A...",
        ...
      },
      "low": { ... },
      ...
    }
  }
}
```

### Key Fields

- **`id`**: Unique identifier (format: `brand.model.version`)
- **`verified`**: `true` only after real AC testing; `false` for new/imported packs
- **`capabilities`**: Declares supported HVAC/fan/swing modes
- **`commands`**: Nested dict mapping states → payloads
- **`notes`**: Human-readable status (e.g., "Verified cool-only" or "Partial: heat mode under expansion")

---

## Workflow 1: Importing an Existing Matrix

### Scenario
You have a command matrix from another Home Assistant integration or a raw export file.

### Option A: Flat Matrix (Python dict)

If you have a flat structure like:
```python
{
  "cool_18_auto": "PAYLOAD_1",
  "cool_19_auto": "PAYLOAD_2",
  "cool_18_low": "PAYLOAD_3",
  ...
}
```

Use the **import utility**:

```python
from custom_components.aerostate.packs.pack_import import (
    convert_flat_matrix_to_pack,
    validate_imported_pack,
    export_pack_to_json_string,
)

flat_matrix = {
    "off": "PAYLOAD_OFF",
    "cool_18_auto": "PAYLOAD_1",
    "cool_19_auto": "PAYLOAD_2",
    ...
}

pack = convert_flat_matrix_to_pack(
    flat_matrix=flat_matrix,
    brand="LG",
    model="PC09SQ NSJ",
    min_temperature=18,
    max_temperature=30,
    temperature_step=1,
    hvac_modes=["cool"],
    fan_modes=["auto", "low", "mid", "high"],
)

# Validate
issues = validate_imported_pack(pack)
if issues:
    print("Validation issues:", issues)

# Export
json_str = export_pack_to_json_string(pack, pretty=True)
with open("packs/builtin/lg/pc09sq_nsj_v1.json", "w") as f:
    f.write(json_str)
```

### Option B: CSV Matrix

If you have a CSV file like:
```
HVAC Mode, Fan Mode, 18, 19, 20, ..., 30
cool,      auto,     PAYLOAD_1, PAYLOAD_2, ...
cool,      low,      PAYLOAD_3, PAYLOAD_4, ...
```

Use the CSV converter:

```python
from custom_components.aerostate.packs.pack_import import (
    convert_csv_matrix_to_pack,
)

csv_content = """
HVAC Mode, Fan Mode, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
cool,      auto,     PL1, PL2, PL3, ..., PL13
cool,      low,      PL1, PL2, PL3, ..., PL13
cool,      mid,      PL1, PL2, PL3, ..., PL13
cool,      high,     PL1, PL2, PL3, ..., PL13
"""

pack = convert_csv_matrix_to_pack(
    csv_content=csv_content,
    brand="LG",
    model="PC09SQ NSJ",
)
```

---

## Workflow 2: Expanding a Verified Pack

### Scenario
The LG pack is verified for COOL mode. You want to add HEAT mode.

### Step 1: Collect Verified Payloads

**Important:** Do NOT guess or copy payloads from other projects. You must:
1. Have real AC hardware available
2. Use Broadlink remote to capture actual IR codes
3. Test each code on the real AC unit
4. Document which specific AC model/revision each code works on

### Step 2: Create Expansion Template

Use the authoring utility to generate a template:

```python
from custom_components.aerostate.packs.pack_authoring import (
    suggest_pack_expansion,
    validate_matrix_structure,
)
import json

# Load current verified pack
with open("packs/builtin/lg/pc09sq_nsj_v1.json") as f:
    current_pack = json.load(f)

# Suggest expansion with heat mode (use cool as template initially)
expanded = suggest_pack_expansion(
    current_pack=current_pack,
    new_hvac_mode="heat",
    template_mode="cool",  # Copies structure from cool
)

# This generates:
# {
#   "cool": { ...existing cool payloads... },
#   "heat": { "auto": {...}, "low": {...}, ... }  # Templated structure, ready for real payloads
# }
```

### Step 3: Fill in Real Payloads

Replace placeholder payloads with verified codes:

```python
# Manually update with real codes you tested
expanded["commands"]["heat"]["auto"]["18"] = "REAL_HEAT_AUTO_18_FROM_AC"
expanded["commands"]["heat"]["auto"]["19"] = "REAL_HEAT_AUTO_19_FROM_AC"
# ... repeat for all temps and fan modes
```

### Step 4: Validate Completeness

Check that all required branches exist:

```python
from custom_components.aerostate.packs.pack_authoring import (
    validate_matrix_structure,
    describe_pack_expansion_readiness,
)

capabilities = expanded["capabilities"]
hvac_modes = capabilities["hvac_modes"]  # ["cool", "heat"]
fan_modes = capabilities["fan_modes"]    # ["auto", "low", "mid", "high"]

reports = validate_matrix_structure(
    commands=expanded["commands"],
    min_temp=expanded["min_temperature"],
    max_temp=expanded["max_temperature"],
    temp_step=expanded["temperature_step"],
    expected_fan_modes=fan_modes,
    expected_swing_v=capabilities["swing_vertical_modes"],
    expected_swing_h=capabilities["swing_horizontal_modes"],
)

# Check each mode
for mode_name, report in reports.items():
    print(f"{mode_name}: {report.summary}")
    if not report.is_complete:
        for gap in report.gaps:
            print(f"  - {gap.gap_type}: {gap.details}")
```

### Step 5: Document in Notes

Update the `notes` field to reflect partial support:

```python
expanded["notes"] = "Verified cool-only and heat mode (18-30°C, all fan modes). No swing payloads yet."
expanded["pack_version"] = 2  # Increment version for new pack release
expanded["verified"] = True  # Only after real AC testing complete
```

### Step 6: Test Coverage

Run the coverage report tool:

```python
from custom_components.aerostate.packs.pack_authoring import (
    describe_pack_expansion_readiness,
)

summary = describe_pack_expansion_readiness(expanded)
print(summary)

# Output:
# Pack: lg.pc09sq_nsj.v2
# ...
# Current Coverage: 100.0%
# (means all declared modes/fans/temps have payloads)
```

---

## Workflow 3: Swing Mode Support

### Scenario
AC supports swing (vertical and/or horizontal). You want to add `swing_vertical` and `swing_horizontal` modes.

### Challenge
Swing usually requires additional factors:
- **Swing speed levels** (e.g., slow, fast)
- **Swing direction codes** (e.g., swing up-down, left-right)
- **Interaction with fan modes** (some combos might not work)

### Recommended Approach

Start **without** swing support, then add incrementally:

1. **Phase 1 (Pilot):** Cool + heat with 4 fan modes, NO swing
   - `capabilities.swing_vertical_modes = []`
   - `capabilities.swing_horizontal_modes = []`

2. **Phase 2 (Post-Pilot):** Add swing if AC supports it
   - Collect real swing payloads from AC
   - Test each swing level + fan mode combination
   - Document unsupported combos in notes

3. **Phase 3:** Update pack with swing
   ```python
   expanded["capabilities"]["swing_vertical_modes"] = ["on", "off"]
   # Add nested swing branch: cool -> auto -> on -> 18 -> payload
   # Structure becomes: { hvac_mode -> swing_mode -> fan_mode -> temp -> payload }
   ```

### Rule of Thumb
**Only add features when you have verified, tested payloads for them.** Do not try to infer swing payloads from other packs.

---

## Workflow 4: Contributing a New Pack

### Requirements
1. **AC Model:** You must have real hardware access
2. **Broadlink Remote:** Tested and working with your AC
3. **Command Matrix:** All payloads captured and tested on real AC
4. **Documentation:** Model number, region, any quirks

### Steps

1. **Create pack JSON:**
   ```python
   new_pack = {
       "id": "daikin.ftq60c.v1",
       "brand": "Daikin",
       "models": ["FTQ60C"],
       "transport": "broadlink_base64",
       "min_temperature": 16,
       "max_temperature": 32,
       "temperature_step": 1,
       "verified": False,  # Start unverified
       "notes": "Imported from RA... testing required on real AC",
       "pack_version": 1,
       "capabilities": { ... },
       "commands": { ... },
   }
   ```

2. **Validate locally:**
   ```python
   from custom_components.aerostate.packs.pack_authoring import validate_matrix_structure
   
   reports = validate_matrix_structure(...)
   for mode_name, report in reports.items():
       print(f"{mode_name}: {report.coverage_percentage}%")
   ```

3. **Fork repository and create PR:**
   - Add pack to `packs/builtin/daikin/ftq60c_v1.json`
   - Include description of testing performed
   - Link to GitHub issue with AC model/notes

4. **Maintainers will:**
   - Review pack format and completeness
   - Request real AC testing evidence if needed
   - Merge with `verified: false` for beta
   - Update after community testing → `verified: true`

---

## Troubleshooting

### "Missing temperature 25°C"
Validation detected a gap in your matrix. Solution:
- Did you forget to capture that temperature?
- Add the missing payload: `expanded["commands"]["cool"]["auto"]["25"] = "YOUR_PAYLOAD"`

### "HVAC mode 'heat' not in commands"
You declared heat in `capabilities.hvac_modes` but didn't provide commands.
- Either remove from capabilities, or
- Add `"heat": { "auto": {...}, ... }` to commands

### "Mode is direct payload, not nested"
Old format detected. Your mode structure should be:
```json
{
  "cool": {
    "auto": {
      "18": "PAYLOAD"
    }
  }
}
```
NOT:
```json
{
  "cool": "PAYLOAD"
}
```

### "Imported pack has verified=true"
AeroState auto-detects this and raises a warning. Imported packs must start with `verified: false` until proven on real hardware.

---

## Testing Your Pack Locally

### Add to `packs/builtin/`

```
custom_components/aerostate/packs/builtin/
└── yourcompany/
    └── yourmodel_v1.json
```

### Run Integration Tests

```bash
pytest tests/ -v -k "pack" --tb=short
```

### Manual Testing in Home Assistant

1. Restart Home Assistant
2. Add config entry for your pack
3. Link Broadlink entity
4. Run **Services > aerostate.run_self_test** with profile: **Full**
5. Check thermostat card controls match your capabilities

---

## Tools Reference

### `validate_matrix_structure()`
Checks if all declared modes/fans/temps have payloads.

```python
from custom_components.aerostate.packs.pack_authoring import validate_matrix_structure

reports = validate_matrix_structure(
    commands=pack["commands"],
    min_temp=18,
    max_temp=30,
    temp_step=1,
    expected_fan_modes=["auto", "low", "mid", "high"],
    expected_swing_v=[],
    expected_swing_h=[],
)

for mode, report in reports.items():
    print(f"{mode}: {'✓ complete' if report.is_complete else f'✗ {report.coverage_percentage}%'}")
```

### `describe_pack_expansion_readiness()`
Generates human-readable status summary.

```python
from custom_components.aerostate.packs.pack_authoring import describe_pack_expansion_readiness

summary = describe_pack_expansion_readiness(pack)
print(summary)
# Output:
# Pack: lg.pc09sq_nsj.v1
# Brand: LG | Model: PC09SQ NSJ
# ...
# Current Coverage: 100.0%
```

### `suggest_pack_expansion()`
Creates template for adding new HVAC mode.

```python
from custom_components.aerostate.packs.pack_authoring import suggest_pack_expansion

expanded = suggest_pack_expansion(
    current_pack=cool_pack,
    new_hvac_mode="heat",
    template_mode="cool",  # Use cool structure as template
)
# Now fill in real payloads for heat mode
```

### `convert_flat_matrix_to_pack()`
Transform flat key-value matrix to AeroState pack.

```python
from custom_components.aerostate.packs.pack_import import convert_flat_matrix_to_pack

pack = convert_flat_matrix_to_pack(
    flat_matrix={"cool_18_auto": "PL1", "cool_19_auto": "PL2", ...},
    brand="LG",
    model="Test",
    hvac_modes=["cool"],
    fan_modes=["auto"],
)
```

---

## Common Patterns

### Adding a New Brand

1. Create folder: `packs/builtin/newbrand/`
2. Create pack: `newbrand/somemodel_v1.json`
3. Use `convert_flat_matrix_to_pack()` or `convert_csv_matrix_to_pack()` to generate
4. Fill in real payloads
5. Validate with `validate_matrix_structure()`
6. Set `verified: false` initially
7. Submit PR for review

### Incrementally Expanding a Pack

1. Start with 1 HVAC mode (cool) ← Current: LG pack
2. Add 2nd HVAC mode (heat) with real payloads ← Next: v0.1.1
3. Add 3rd HVAC mode (dry) with real payloads ← Future: v0.1.2
4. Add swing only after ALL modes have payloads ← Future: v0.2.0

### Handling Quirks

Document in `notes` field:

```json
{
  "notes": "Verified cool/heat modes. Quirk: Daikin FTQ60C requires 500ms delay between mode changes on some hardware revisions. Use aerostate.run_self_test with profile=full to validate."
}
```

---

## Best Practices

1. **Always test on real hardware** before claiming `verified: true`
2. **Document the AC model and region** (codes vary by country)
3. **Start with one mode, expand incrementally** (cool → heat → dry)
4. **Never copy payloads** from other projects without testing
5. **Use the validation tools** to catch gaps before testing in HA
6. **Keep notes updated** as you expand and test
7. **Run full test suite** with your pack: `pytest -v`

---

**Questions?** Open an issue at:  
https://github.com/srobysingh-bot/aerostate/issues

**Ready to contribute a pack?** Submit a PR with your pack JSON + description of testing performed. 🎉
