"""The no-model fallback for the "How to Prepare" panel.

`rule_clean` is what an operator actually reads whenever no LLM is configured,
which is the default state of a fresh checkout -- so it is not a cosmetic path.
These tests pin the two things that made it unreadable and the one thing that
made it destructive.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from racik.recipe_text import CHATTER_MAX_CHARS, rule_clean

# Real text from dish 66374, the one that surfaced this.
SCRAPED = (
    "Siapkan bahan-bahan. _________________________________ Goreng ikan "
    "manyung asap (ikan cucut asap) dan tahu. Rebus bayam. "
    "_________________________________ Rebus juga bahan sambal. >> Uleg "
    "bahan sambal. Plecing bayam jebrot manyung asap dan tahu siap "
    "disajikan ! Sungguh nikmat !!\U0001F60B >> Sudah pasti nambah yak "
    "\U0001F602\U0001F92D"
)


class TestDividers:
    def test_a_run_of_underscores_never_reaches_a_step(self):
        # `_` is a word character, so the `^\W*$` test cannot catch a line of
        # underscores -- and the divider sits inline, so it used to arrive
        # glued to the front of the next instruction.
        steps = rule_clean(SCRAPED)
        assert not any("___" in s for s in steps)
        assert "Goreng ikan manyung asap (ikan cucut asap) dan tahu" in steps

    @pytest.mark.parametrize("divider", ["___", "-----", "=====", "~~~~", "***", "———"])
    def test_every_divider_style_is_stripped(self, divider):
        steps = rule_clean("Rebus bayam. %s Goreng tahu." % divider)
        assert steps == ["Rebus bayam", "Goreng tahu"]

    def test_a_hyphenated_word_survives(self):
        # "bahan-bahan" and "potong-potong" are ordinary Indonesian
        # reduplication, not dividers. Only a run of three or more counts.
        assert rule_clean("Siapkan bahan-bahan.") == ["Siapkan bahan-bahan"]
        assert rule_clean("Potong-potong kentang.") == ["Potong-potong kentang"]


class TestChatter:
    def test_a_short_sign_off_is_dropped(self):
        steps = rule_clean(SCRAPED)
        assert not any("nikmat" in s.lower() for s in steps)
        assert not any("nambah" in s.lower() for s in steps)

    def test_emoji_never_reach_a_step(self):
        assert "\U0001F60B" not in " ".join(rule_clean(SCRAPED))

    def test_chatter_inside_a_long_instruction_does_not_delete_it(self):
        """The regression this guard exists for.

        Many scraped recipes carry no sentence-ending punctuation at all, so
        the whole method arrives as ONE part. Testing that part with a bare
        `search` for chatter deleted the entire recipe over a single phrase --
        20 dishes in a 1,500-dish sample came back with no steps whatsoever.
        """
        long_instruction = (
            "Tumis bumbu halus dan daun aromatik hingga harum lalu masukkan "
            "santan dan aduk perlahan sampai mendidih agar tidak pecah "
            "kemudian angkat dan siap disantap bersama nasi hangat"
        )
        assert len(long_instruction) > CHATTER_MAX_CHARS
        assert rule_clean(long_instruction) == [
            long_instruction[:1].upper() + long_instruction[1:]]

    def test_no_recipe_with_real_instructions_is_emptied(self):
        # Guards the same failure from the other direction: whatever the
        # filters do, a method that contains cooking must not vanish.
        assert rule_clean("Rebus air. Masukkan mie. Siap disantap.") == [
            "Rebus air", "Masukkan mie"]
