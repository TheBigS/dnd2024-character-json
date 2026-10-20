#!/usr/bin/env python3
"""Schema regression tests for the D&D 2024 Character JSON spec."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "character.schema.json"
CHARACTERS_DIR = ROOT / "characters"
EXAMPLES_DIR = ROOT / "spec" / "examples"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def minimal_character(**overrides) -> dict:
    base = {
        "spec_version": "1.1.0",
        "name": "Test Character",
        "species": {"name": "Human"},
        "classes": [{"name": "Fighter", "level": 1}],
        "abilities": {"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 8},
    }
    base.update(overrides)
    return base


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema()
        cls.validator = Draft202012Validator(cls.schema)

    def assert_valid(self, doc: dict) -> None:
        errors = sorted(self.validator.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            detail = "; ".join(
                "{}: {}".format("/".join(str(p) for p in e.path) or "(root)", e.message)
                for e in errors
            )
            self.fail("unexpected validation errors: " + detail)

    def assert_invalid(self, doc: dict) -> None:
        with self.assertRaises(ValidationError):
            self.validator.validate(doc)

    def test_schema_version_is_1_1_0(self) -> None:
        self.assertEqual(self.schema.get("version"), "1.1.0")

    def test_bundled_character_files_validate(self) -> None:
        files = sorted(CHARACTERS_DIR.glob("*.json"))
        self.assertTrue(files, "expected example characters")
        for path in files:
            with self.subTest(path.name):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assert_valid(doc)

    def test_spec_examples_validate(self) -> None:
        files = sorted(EXAMPLES_DIR.glob("*.json"))
        self.assertTrue(files, "expected spec examples")
        for path in files:
            with self.subTest(path.name):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assert_valid(doc)

    def test_legacy_integer_spell_slots_still_valid(self) -> None:
        doc = minimal_character(spell_slots={"1": 4, "2": 2})
        self.assert_valid(doc)

    def test_object_spell_slots_with_expended(self) -> None:
        doc = minimal_character(
            spell_slots={
                "1": {"total": 4, "expended": 1},
                "2": {"total": 2, "expended": 0},
            }
        )
        self.assert_valid(doc)

    def test_spell_slots_object_requires_total(self) -> None:
        doc = minimal_character(spell_slots={"1": {"expended": 1}})
        self.assert_invalid(doc)

    def test_resources_pool(self) -> None:
        doc = minimal_character(
            resources=[
                {"name": "Ki", "current": 2, "maximum": 3},
                {"name": "Second Wind", "maximum": 1},
            ]
        )
        self.assert_valid(doc)

    def test_resources_require_name_and_maximum(self) -> None:
        doc = minimal_character(resources=[{"name": "Ki"}])
        self.assert_invalid(doc)

    def test_prepared_count(self) -> None:
        doc = minimal_character(prepared_count=6)
        self.assert_valid(doc)

    def test_prepared_count_rejects_negative(self) -> None:
        doc = minimal_character(prepared_count=-1)
        self.assert_invalid(doc)

    def test_pact_slots(self) -> None:
        doc = minimal_character(pact_slots={"total": 2, "expended": 1, "level": 2})
        self.assert_valid(doc)

    def test_pact_slots_require_total(self) -> None:
        doc = minimal_character(pact_slots={"expended": 0, "level": 1})
        self.assert_invalid(doc)

    def test_equipment_string_and_object_mix(self) -> None:
        doc = minimal_character(
            equipment=[
                "Backpack",
                {"name": "Dagger", "quantity": 2, "equipped": True},
                {"name": "Rope", "notes": "50 ft. hempen"},
            ]
        )
        self.assert_valid(doc)

    def test_equipment_object_requires_name(self) -> None:
        doc = minimal_character(equipment=[{"quantity": 1}])
        self.assert_invalid(doc)

    def test_unknown_top_level_property_still_rejected(self) -> None:
        doc = minimal_character(not_a_real_field=True)
        self.assert_invalid(doc)

    def test_hit_points_current_and_temp_remain_valid(self) -> None:
        doc = minimal_character(
            hit_points={"max": 20, "current": 12, "temp": 3},
            hit_dice={"die": "d10", "total": 2, "spent": 1},
            death_saves={"successes": 1, "failures": 0},
        )
        self.assert_valid(doc)

    def test_live_play_example_round_trips(self) -> None:
        path = EXAMPLES_DIR / "live-play-state.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc.get("spec_version"), "1.1.0")
        self.assert_valid(doc)
        self.assertIn("resources", doc)
        self.assertIsInstance(doc["spell_slots"]["1"], dict)
        # Mutation that breaks spell slot shape should fail.
        bad = copy.deepcopy(doc)
        bad["spell_slots"]["1"] = {"expended": 1}
        self.assert_invalid(bad)


if __name__ == "__main__":
    unittest.main()
