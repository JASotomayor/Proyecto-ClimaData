"""Fetch NASA POWER daily climate data for Campo Trebolares and save to disk.

Run once from the project root:
    python scripts/01_fetch_climate.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.climate import (
    compute_agroclimatic_indicators,
    fetch_nasa_power_daily,
    prepare_climate_outputs,
)
from src.config import MIN_NASA_YEAR

LAT = -35.5598
LON = -63.5924
START_YEAR = MIN_NASA_YEAR
END_YEAR = max(MIN_NASA_YEAR, datetime.now(timezone.utc).year - 1)

RAW_DIR = Path("data/trebolares/raw")
PROC_DIR = Path("data/trebolares/processed")


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching NASA POWER {START_YEAR}–{END_YEAR}  lat={LAT}  lon={LON}")
    daily = fetch_nasa_power_daily(LAT, LON, START_YEAR, END_YEAR)

    raw_path = RAW_DIR / "climate_daily.parquet"
    daily.to_parquet(raw_path, index=False)
    print(f"  ✓ {len(daily):,} rows  →  {raw_path}")

    print("Processing aggregates...")
    outputs = prepare_climate_outputs(daily)

    outputs["annual"].to_parquet(PROC_DIR / "climate_annual.parquet", index=False)
    outputs["monthly_by_year"].to_parquet(
        PROC_DIR / "climate_monthly_by_year.parquet", index=False
    )
    # Reset Categorical before saving so parquet round-trips cleanly
    mc = outputs["monthly_climatology"].copy()
    mc["month_label"] = mc["month_label"].astype(str)
    mc.to_parquet(PROC_DIR / "climate_monthly_climatology.parquet", index=False)

    indicators = compute_agroclimatic_indicators(
        outputs["annual"], outputs["monthly_climatology"]
    )
    with open(PROC_DIR / "climate_indicators.json", "w", encoding="utf-8") as f:
        json.dump(dict(indicators), f, ensure_ascii=False, indent=2)

    print(f"  ✓ annual          : {len(outputs['annual'])} years")
    print(f"  ✓ monthly_by_year : {len(outputs['monthly_by_year'])} rows")
    print(f"  ✓ indicators      : {PROC_DIR / 'climate_indicators.json'}")
    print("Done.\n")


if __name__ == "__main__":
    main()
