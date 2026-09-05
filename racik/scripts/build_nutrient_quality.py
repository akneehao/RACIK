"""Export how much of TKPI was measured rather than estimated.

The CSV this project ships (`TKPI_2020_Table_4_All_Data.csv`) carries values but
not their provenance: a number that was measured in a lab and a number that was
inferred from a similar food look identical in it. A separately maintained
Supabase copy of the same table does carry a per-value `is_imputed` flag, and
that flag turns out to matter a great deal.

Weighted across the table, only 68% of fibre values were measured. Sodium is 53%,
zinc 47%, beta-carotene 39%. Meanwhile calcium and iron -- which `akg.py`
classes as advisory because secondary sources disagree on the TARGET -- are 99.6%
and 99.3% measured, so the weakness there is the reference figure, not the food
data.

Those are two independent axes of uncertainty and a nutrient needs both to hold
before a hard floor on it means anything:

    is the TARGET right?        akg.py, from Permenkes transcription
    is the MEASUREMENT right?   this file, from TKPI provenance

This script writes the second one to a small JSON committed alongside the data,
so the engine never depends on Supabase at runtime -- it reads twenty-odd numbers
from a file. Re-run it only if the upstream table is refreshed.

    python scripts/build_nutrient_quality.py
"""
from __future__ import annotations

import collections
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_PATH = PROJECT_DIR / "data" / "nutrient_quality.json"

# Supabase nutrient codes -> the keys akg.py uses.
KEY_MAP = {
    "energy_kcal": "energy_kcal",
    "protein_g": "protein_g",
    "fat_g": "fat_g",
    "carbohydrate_g": "carb_g",
    "fibre_g": "fibre_g",
    "calcium_mg": "calcium_mg",
    "iron_mg": "iron_mg",
    "zinc_mg": "zinc_mg",
    "retinol_mcg": "vit_a_mcg",
    "vitamin_c_mg": "vit_c_mg",
    "sodium_mg": "sodium_mg",
}

PAGE = 1000


def _env(name):
    value = os.environ.get(name)
    if value:
        return value
    for candidate in (PROJECT_DIR / ".env", PROJECT_DIR.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            for prefix in ("set ", "export "):
                if key.lower().startswith(prefix):
                    key = key[len(prefix):].strip()
            if key == name:
                return val.strip().strip('"').strip("'")
    return None


def _fetch(url, key, table, select, offset):
    query = urllib.parse.urlencode({"select": select, "offset": offset, "limit": PAGE})
    request = urllib.request.Request("%s/%s?%s" % (url.rstrip("/"), table, query))
    request.add_header("apikey", key)
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY not found; leaving the existing file alone.")
        return 1

    present = collections.Counter()
    measured = collections.Counter()
    offset = 0
    while True:
        rows = _fetch(url, key, "food_nutrient", "nutrient_code,value,is_imputed", offset)
        if not rows:
            break
        for row in rows:
            if row.get("value") is None:
                continue
            code = row["nutrient_code"]
            present[code] += 1
            if not row.get("is_imputed"):
                measured[code] += 1
        if len(rows) < PAGE:
            break
        offset += PAGE

    foods = 0
    offset = 0
    while True:
        rows = _fetch(url, key, "food", "code", offset)
        foods += len(rows)
        if len(rows) < PAGE:
            break
        offset += PAGE

    out = {
        "_source": "Supabase food_nutrient.is_imputed, TKPI 2020",
        "_generated": date.today().isoformat(),
        "_foods": foods,
        "_note": ("measured_fraction is the share of PRESENT values that were "
                  "measured rather than imputed; coverage is the share of foods "
                  "carrying any value at all."),
        "nutrients": {},
    }
    for code, count in sorted(present.items()):
        mapped = KEY_MAP.get(code)
        if not mapped:
            continue
        out["nutrients"][mapped] = {
            "tkpi_code": code,
            "coverage": round(count / foods, 4) if foods else 0.0,
            "measured_fraction": round(measured[code] / count, 4) if count else 0.0,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("wrote %s (%d nutrients, %d foods)" % (OUT_PATH, len(out["nutrients"]), foods))
    for name, v in sorted(out["nutrients"].items(), key=lambda kv: kv[1]["measured_fraction"]):
        print("  %-14s coverage %5.1f%%  measured %5.1f%%"
              % (name, v["coverage"] * 100, v["measured_fraction"] * 100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
