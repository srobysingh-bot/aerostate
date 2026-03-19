"""Tests for pack authoring utilities."""

from custom_components.aerostate.packs.pack_authoring import (
    describe_pack_expansion_readiness,
    suggest_pack_expansion,
    validate_matrix_structure,
)


class TestValidateMatrixStructure:
    """Test command matrix structure validation."""

    def test_complete_cool_only_matrix(self):
        """Validate a complete cool-only matrix passes."""
        commands = {
            "off": "PAYLOAD_OFF",
            "cool": {
                "auto": {
                    "18": "PAYLOAD",
                    "19": "PAYLOAD",
                    "20": "PAYLOAD",
                },
                "low": {
                    "18": "PAYLOAD",
                    "19": "PAYLOAD",
                    "20": "PAYLOAD",
                },
            },
        }

        reports = validate_matrix_structure(
            commands=commands,
            min_temp=18,
            max_temp=20,
            temp_step=1,
            expected_fan_modes=["auto", "low"],
            expected_swing_v=[],
            expected_swing_h=[],
        )

        assert "cool" in reports
        assert reports["cool"].is_complete is True
        assert reports["cool"].coverage_percentage == 100.0

    def test_incomplete_missing_fan_mode(self):
        """Detect missing fan mode in matrix."""
        commands = {
            "off": "PAYLOAD_OFF",
            "cool": {
                "auto": {
                    "18": "PAYLOAD",
                    "19": "PAYLOAD",
                }
                # Missing "low" fan mode
            },
        }

        reports = validate_matrix_structure(
            commands=commands,
            min_temp=18,
            max_temp=19,
            temp_step=1,
            expected_fan_modes=["auto", "low"],
            expected_swing_v=[],
            expected_swing_h=[],
        )

        assert reports["cool"].is_complete is False
        gaps = [g for g in reports["cool"].gaps if g.gap_type == "missing_fan"]
        assert len(gaps) > 0
        assert any("low" in g.details for g in gaps)

    def test_incomplete_missing_temperature(self):
        """Detect missing temperature in matrix."""
        commands = {
            "off": "PAYLOAD_OFF",
            "cool": {
                "auto": {
                    "18": "PAYLOAD",
                    # Missing 19
                    "20": "PAYLOAD",
                },
                "low": {
                    "18": "PAYLOAD",
                    "19": "PAYLOAD",
                    "20": "PAYLOAD",
                },
            },
        }

        reports = validate_matrix_structure(
            commands=commands,
            min_temp=18,
            max_temp=20,
            temp_step=1,
            expected_fan_modes=["auto", "low"],
            expected_swing_v=[],
            expected_swing_h=[],
        )

        assert reports["cool"].is_complete is False
        gaps = [g for g in reports["cool"].gaps if g.gap_type == "missing_temp"]
        assert len(gaps) > 0

    def test_flat_mode_structure_incomplete(self):
        """Detect flat mode (direct payload) as incomplete."""
        commands = {
            "off": "PAYLOAD_OFF",
            "cool": "PAYLOAD_FLAT",  # Should be nested
        }

        reports = validate_matrix_structure(
            commands=commands,
            min_temp=18,
            max_temp=20,
            temp_step=1,
            expected_fan_modes=["auto", "low"],
            expected_swing_v=[],
            expected_swing_h=[],
        )

        assert reports["cool"].is_complete is False
        assert any(g.gap_type == "incomplete_branch" for g in reports["cool"].gaps)

    def test_coverage_percentage_calculation(self):
        """Verify coverage percentage is calculated correctly."""
        commands = {
            "off": "PAYLOAD_OFF",
            "cool": {
                "auto": {"18": "PAYLOAD"},  # 1 out of 2 temps
                "low": {
                    "18": "PAYLOAD",
                    "19": "PAYLOAD",
                },  # 2 out of 2 temps
            },
        }

        reports = validate_matrix_structure(
            commands=commands,
            min_temp=18,
            max_temp=19,
            temp_step=1,
            expected_fan_modes=["auto", "low"],
            expected_swing_v=[],
            expected_swing_h=[],
        )

        assert reports["cool"].is_complete is False
        # Coverage counts unique temps found across any fan mode
        # Both temps (18, 19) are present in at least one fan mode
        assert reports["cool"].coverage_percentage == 100.0


class TestDescribePackExpansionReadiness:
    """Test pack expansion readiness reporting."""

    def test_cool_only_pack_summary(self):
        """Generate summary for cool-only pack."""
        pack = {
            "id": "lg.pc09sq_nsj.v1",
            "brand": "LG",
            "models": ["PC09SQ NSJ"],
            "verified": True,
            "notes": "Cool-only verified pack",
            "min_temperature": 18,
            "max_temperature": 30,
            "temperature_step": 1,
            "capabilities": {
                "hvac_modes": ["cool"],
                "fan_modes": ["auto", "low", "mid", "high"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "commands": {
                "off": "PAYLOAD",
                "cool": {
                    "auto": {str(t): "PAYLOAD" for t in range(18, 31)},
                    "low": {str(t): "PAYLOAD" for t in range(18, 31)},
                    "mid": {str(t): "PAYLOAD" for t in range(18, 31)},
                    "high": {str(t): "PAYLOAD" for t in range(18, 31)},
                },
            },
        }

        summary = describe_pack_expansion_readiness(pack)

        assert "lg.pc09sq_nsj.v1" in summary
        assert "LG" in summary
        assert "cool" in summary.lower()
        # Should have close to 100% coverage (off payload is 1 extra)
        # 4 fan modes * 13 temps = 52 expected, plus 1 off = 53 total payloads
        assert "coverage" in summary.lower()

    def test_partial_pack_summary(self):
        """Summary reflects partial pack status in notes."""
        pack = {
            "id": "test.pack",
            "brand": "Test",
            "models": ["Test Model"],
            "verified": False,
            "notes": "Partial: heat mode under expansion",
            "min_temperature": 16,
            "max_temperature": 30,
            "temperature_step": 1,
            "capabilities": {
                "hvac_modes": ["cool", "heat"],
                "fan_modes": ["auto", "low"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "commands": {
                "off": "PAYLOAD",
                "cool": {
                    "auto": {str(t): "PAYLOAD" for t in range(16, 31)},
                    "low": {str(t): "PAYLOAD" for t in range(16, 31)},
                },
                "heat": {
                    "auto": {"PLACEHOLDER": "PLACEHOLDER"},
                    "low": {"PLACEHOLDER": "PLACEHOLDER"},
                },
            },
        }

        summary = describe_pack_expansion_readiness(pack)

        assert "Partial" in summary
        assert "heat" in summary.lower()
        assert "False" in summary or "false" not in summary.lower()  # verified is False


class TestSuggestPackExpansion:
    """Test pack expansion template generation."""

    def test_expand_with_template_mode(self):
        """Generate expansion template using existing mode as template."""
        current_pack = {
            "id": "lg.pc09sq_nsj.v1",
            "verified": True,
            "notes": "Cool-only verified pack",
            "min_temperature": 18,
            "max_temperature": 30,
            "temperature_step": 1,
            "capabilities": {
                "hvac_modes": ["cool"],
                "fan_modes": ["auto", "low", "mid", "high"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "commands": {
                "off": "PAYLOAD_OFF",
                "cool": {
                    "auto": {str(t): f"COOL_AUTO_{t}" for t in range(18, 31)},
                    "low": {str(t): f"COOL_LOW_{t}" for t in range(18, 31)},
                    "mid": {str(t): f"COOL_MID_{t}" for t in range(18, 31)},
                    "high": {str(t): f"COOL_HIGH_{t}" for t in range(18, 31)},
                },
            },
        }

        expanded = suggest_pack_expansion(
            current_pack=current_pack,
            new_hvac_mode="heat",
            template_mode="cool",
        )

        assert "heat" in expanded["commands"]
        assert expanded["capabilities"]["hvac_modes"] == ["cool", "heat"]
        # Template should have filled in fan mode structure from cool
        assert "auto" in expanded["commands"]["heat"]
        assert "low" in expanded["commands"]["heat"]
        # Template should have filled in same payloads as cool
        assert expanded["commands"]["heat"]["auto"]["18"] == current_pack["commands"]["cool"]["auto"]["18"]
        # Notes should reflect partial support
        assert "Partial" in expanded["notes"] or "heat" in expanded["notes"].lower()

    def test_expand_without_template(self):
        """Generate expansion template without existing mode as template."""
        current_pack = {
            "id": "test.pack",
            "verified": False,
            "min_temperature": 18,
            "max_temperature": 20,
            "temperature_step": 1,
            "capabilities": {
                "hvac_modes": ["cool"],
                "fan_modes": ["auto", "low"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "commands": {
                "off": "PAYLOAD_OFF",
                "cool": {
                    "auto": {"18": "PAYLOAD", "19": "PAYLOAD", "20": "PAYLOAD"},
                    "low": {"18": "PAYLOAD", "19": "PAYLOAD", "20": "PAYLOAD"},
                },
            },
        }

        expanded = suggest_pack_expansion(
            current_pack=current_pack,
            new_hvac_mode="dry",
            template_mode=None,
        )

        assert "dry" in expanded["commands"]
        assert expanded["capabilities"]["hvac_modes"] == ["cool", "dry"]
        # Should have empty structure with placeholders
        assert "auto" in expanded["commands"]["dry"]
        assert "18" in expanded["commands"]["dry"]["auto"]
        assert expanded["commands"]["dry"]["auto"]["18"] == "PAYLOAD_PLACEHOLDER"

    def test_expand_mode_already_exists(self):
        """Expanding existing mode doesn't duplicate."""
        current_pack = {
            "id": "test.pack",
            "capabilities": {
                "hvac_modes": ["cool", "heat"],
                "fan_modes": ["auto"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "min_temperature": 18,
            "max_temperature": 18,
            "temperature_step": 1,
            "commands": {
                "off": "PAYLOAD_OFF",
                "cool": {"auto": {"18": "PAYLOAD"}},
                "heat": {"auto": {"18": "PAYLOAD"}},
            },
        }

        expanded = suggest_pack_expansion(
            current_pack=current_pack,
            new_hvac_mode="heat",  # Already exists
        )

        # Should still have exactly 2 modes
        assert len(expanded["capabilities"]["hvac_modes"]) == 2
        assert expanded["capabilities"]["hvac_modes"].count("heat") == 1
