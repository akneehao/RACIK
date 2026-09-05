"""The binding tier needs a trusted target AND a measured column.

These two tests are the whole point of `data/nutrient_quality.json`. Without
them a future edit could quietly promote fibre back into `BINDING_NUTRIENTS` --
it is a macro, so it looks like it belongs -- and the solve would start
optimising against a column that is two-thirds inferred, with every layer
downstream agreeing because they all read the same column.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from racik.akg import (ADVISORY_NUTRIENTS, BINDING_NUTRIENTS, MACRO_NUTRIENTS,
                       MEASURED_FRACTION_FLOOR, NUTRIENT_META, _measured_fraction,
                       nutrient_quality)

QUALITY_PATH = Path(__file__).resolve().parents[1] / "data" / "nutrient_quality.json"


class TestQualityFile:
    def test_the_file_ships_with_the_repo(self):
        # It is small, static, and regenerating it needs access to an annotated
        # copy of TKPI that not every checkout has. Same treatment as prices_id.
        assert QUALITY_PATH.exists()

    def test_it_records_where_the_numbers_came_from(self):
        payload = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
        assert payload["_source"]
        assert payload["_generated"]

    def test_every_graded_nutrient_is_one_the_engine_knows(self):
        for key in nutrient_quality():
            assert key in NUTRIENT_META, "unknown nutrient key %r" % key

    def test_fractions_are_fractions(self):
        for key, entry in nutrient_quality().items():
            assert 0.0 <= entry["measured_fraction"] <= 1.0, key
            assert 0.0 <= entry["coverage"] <= 1.0, key


class TestBindingTier:
    def test_fibre_does_not_bind(self):
        # A macro, so the target test passes it, but roughly two thirds of its
        # TKPI values are imputed. This is the case the whole mechanism exists for.
        assert _measured_fraction("fibre_g") < MEASURED_FRACTION_FLOOR
        assert "fibre_g" not in BINDING_NUTRIENTS
        assert "fibre_g" in ADVISORY_NUTRIENTS

    @pytest.mark.parametrize("nutrient", ["energy_kcal", "protein_g", "fat_g", "carb_g"])
    def test_the_well_measured_macros_still_bind(self, nutrient):
        assert nutrient in BINDING_NUTRIENTS

    def test_micros_never_bind_however_well_measured(self):
        # Calcium and iron are ~99% measured, so the food data is sound; the AKG
        # reference figure is what is disputed. Good measurement must not promote
        # a nutrient whose target nobody has verified.
        assert _measured_fraction("calcium_mg") > MEASURED_FRACTION_FLOOR
        assert _measured_fraction("iron_mg") > MEASURED_FRACTION_FLOOR
        assert "calcium_mg" not in BINDING_NUTRIENTS
        assert "iron_mg" not in BINDING_NUTRIENTS

    def test_binding_is_a_subset_of_the_macros(self):
        assert set(BINDING_NUTRIENTS) <= set(MACRO_NUTRIENTS)

    def test_the_two_tiers_do_not_overlap_and_cover_everything(self):
        assert not set(BINDING_NUTRIENTS) & set(ADVISORY_NUTRIENTS)
        assert set(BINDING_NUTRIENTS) | set(ADVISORY_NUTRIENTS) == set(NUTRIENT_META)

    def test_a_missing_quality_file_restores_the_old_behaviour(self, monkeypatch):
        # Losing the file must not silently loosen or tighten anything: with no
        # provenance, every nutrient reads as fully measured and the target test
        # alone decides, exactly as before.
        monkeypatch.setattr("racik.akg.nutrient_quality", lambda: {})
        assert _measured_fraction("fibre_g") == 1.0
