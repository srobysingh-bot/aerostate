"""Tests for pack import and conversion utilities."""

import pytest

from custom_components.aerostate.packs.pack_import import (
    ImportError,
    convert_csv_matrix_to_pack,
    convert_flat_matrix_to_pack,
    export_pack_to_json_string,
    validate_imported_pack,
)


class TestConvertFlatMatrixToPack:
    """Test flat matrix to pack conversion."""

    def test_simple_cool_only_flat_matrix(self):
        """Convert simple flat matrix to nested pack."""
        flat_matrix = {
            "cool_18_auto": "PAYLOAD_A",
            "cool_19_auto": "PAYLOAD_B",
            "cool_18_low": "PAYLOAD_C",
            "cool_19_low": "PAYLOAD_D",
        }

        pack = convert_flat_matrix_to_pack(
            flat_matrix=flat_matrix,
            brand="LG",
            model="Test",
            hvac_modes=["cool"],
            fan_modes=["auto", "low"],
        )

        assert pack["brand"] == "LG"
        assert pack["verified"] is False
        assert "cool" in pack["commands"]
        assert "auto" in pack["commands"]["cool"]
        assert pack["commands"]["cool"]["auto"]["18"] == "PAYLOAD_A"
        assert pack["commands"]["cool"]["low"]["19"] == "PAYLOAD_D"

    def test_flat_matrix_with_off_mode(self):
        """Flat matrix with explicit off mode."""
        flat_matrix = {
            "off": "PAYLOAD_OFF",
            "cool_18_auto": "PAYLOAD_A",
        }

        pack = convert_flat_matrix_to_pack(
            flat_matrix=flat_matrix,
            brand="TestBrand",
            model="TestModel",
            hvac_modes=["cool"],
            fan_modes=["auto"],
        )

        assert "off" in pack["commands"]
        assert pack["commands"]["off"] == "PAYLOAD_OFF"

    def test_auto_detect_modes(self):
        """Auto-detect HVAC and fan modes from keys."""
        flat_matrix = {
            "cool_18_auto": "A",
            "cool_19_high": "B",
            "heat_18_low": "C",
            "heat_19_medium": "D",
        }

        pack = convert_flat_matrix_to_pack(
            flat_matrix=flat_matrix,
            brand="Auto",
            model="Detect",
            # Should auto-detect cool, heat, auto, high, low, medium
        )

        hvac_modes = pack["capabilities"]["hvac_modes"]
        fan_modes = pack["capabilities"]["fan_modes"]

        assert "cool" in hvac_modes
        assert "heat" in hvac_modes
        assert "auto" in fan_modes
        assert "high" in fan_modes

    def test_empty_matrix_raises_error(self):
        """Empty flat matrix raises ImportError."""
        with pytest.raises(ImportError, match="cannot be empty"):
            convert_flat_matrix_to_pack(
                flat_matrix={},
                brand="Test",
                model="Test",
            )

    def test_no_detectable_modes_raises_error(self):
        """Matrix with no detectable modes raises ImportError."""
        flat_matrix = {"xyz_123_abc": "PAYLOAD"}

        with pytest.raises(ImportError, match="Could not detect"):
            convert_flat_matrix_to_pack(
                flat_matrix=flat_matrix,
                brand="Test",
                model="Test",
            )


class TestConvertCsvMatrixToPack:
    """Test CSV format matrix conversion."""

    def test_simple_csv_conversion(self):
        """Convert simple CSV to pack."""
        csv_content = """
        HVAC Mode, Fan Mode, 18, 19, 20
        cool,      auto,     payload_1, payload_2, payload_3
        cool,      low,      payload_4, payload_5, payload_6
        """

        pack = convert_csv_matrix_to_pack(
            csv_content=csv_content,
            brand="LG",
            model="Test",
        )

        assert pack["brand"] == "LG"
        assert "cool" in pack["commands"]
        assert "auto" in pack["commands"]["cool"]
        assert pack["commands"]["cool"]["auto"]["18"] == "payload_1"
        assert pack["commands"]["cool"]["low"]["20"] == "payload_6"

    def test_csv_with_missing_payloads(self):
        """CSV with N/A or missing values skip those entries."""
        csv_content = """
        HVAC Mode, Fan Mode, 18, 19, 20
        cool,      auto,     payload_1, N/A, payload_3
        cool,      low,      payload_4, , payload_6
        """

        pack = convert_csv_matrix_to_pack(
            csv_content=csv_content,
            brand="Test",
            model="Test",
        )

        assert pack["commands"]["cool"]["auto"]["18"] == "payload_1"
        assert "19" not in pack["commands"]["cool"]["auto"]  # N/A skipped
        assert "19" not in pack["commands"]["cool"]["low"]  # Empty skipped

    def test_empty_csv_raises_error(self):
        """Empty CSV raises ImportError."""
        with pytest.raises(ImportError):
            convert_csv_matrix_to_pack(
                csv_content="",
                brand="Test",
                model="Test",
            )

    def test_csv_with_no_valid_data_raises_error(self):
        """CSV with headers but no valid payloads raises ImportError."""
        csv_content = """
        HVAC Mode, Fan Mode, 18, 19
        cool,      auto,     N/A, N/A
        """

        with pytest.raises(ImportError, match="No valid payloads"):
            convert_csv_matrix_to_pack(
                csv_content=csv_content,
                brand="Test",
                model="Test",
            )


class TestValidateImportedPack:
    """Test imported pack validation."""

    def test_valid_imported_pack_no_issues(self):
        """Valid imported pack produces no issues."""
        pack = {
            "id": "test.pack.v1",
            "brand": "Test",
            "models": ["Model1"],
            "transport": "broadlink_base64",
            "verified": False,
            "notes": "Test pack",
            "capabilities": {
                "hvac_modes": ["cool"],
                "fan_modes": ["auto"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "commands": {
                "off": "OFF_PAYLOAD",
                "cool": {
                    "auto": {
                        "18": "PAYLOAD",
                    }
                },
            },
        }

        issues = validate_imported_pack(pack)
        assert len(issues) == 0

    def test_missing_required_fields(self):
        """Missing required fields produces issues."""
        pack = {
            "id": "test.pack.v1",
            "brand": "Test",
            # Missing models, transport, capabilities, commands
        }

        issues = validate_imported_pack(pack)
        assert len(issues) > 0
        assert any("required field" in issue for issue in issues)

    def test_verified_imported_pack_has_issue(self):
        """Imported pack with verified=True produces issue."""
        pack = {
            "id": "test.pack.v1",
            "brand": "Test",
            "models": ["Model1"],
            "transport": "broadlink_base64",
            "verified": True,
            "capabilities": {
                "hvac_modes": ["cool"],
                "fan_modes": ["auto"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "commands": {"cool": {"auto": {"18": "PAYLOAD"}}},
        }

        issues = validate_imported_pack(pack)
        assert any("verified=False" in issue for issue in issues)

    def test_missing_hvac_modes(self):
        """Pack with no HVAC modes produces issue."""
        pack = {
            "id": "test.pack.v1",
            "brand": "Test",
            "models": ["Model1"],
            "transport": "broadlink_base64",
            "verified": False,
            "capabilities": {
                "hvac_modes": [],
                "fan_modes": ["auto"],
                "swing_vertical_modes": [],
                "swing_horizontal_modes": [],
            },
            "commands": {},
        }

        issues = validate_imported_pack(pack)
        assert any("HVAC modes" in issue for issue in issues)


class TestExportPackToJson:
    """Test pack JSON export."""

    def test_export_to_json_pretty(self):
        """Export pack to pretty-printed JSON."""
        pack = {
            "id": "test.pack.v1",
            "brand": "Test",
            "capabilities": {"hvac_modes": ["cool"]},
        }

        json_str = export_pack_to_json_string(pack, pretty=True)

        assert '"id"' in json_str
        assert '"test.pack.v1"' in json_str
        assert "\n" in json_str  # Indented

    def test_export_to_json_compact(self):
        """Export pack to compact JSON."""
        pack = {
            "id": "test.pack.v1",
            "brand": "Test",
        }

        json_str = export_pack_to_json_string(pack, pretty=False)

        assert '{"id"' in json_str
        assert '"Test"' in json_str
        # Verify it's valid JSON by parsing it back
        import json

        parsed = json.loads(json_str)
        assert parsed["id"] == "test.pack.v1"
