"""Compute agroclimatic analysis for all 5 crop scenarios and save to disk.

Requires climate data fetched by 01_fetch_climate.py.

Run from the project root:
    python scripts/03_compute_agro.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.agro_scores import run_crop_agro_analysis
from src.config import MIN_NASA_YEAR
from src.crops import list_active_crop_scenarios

LAT = -35.5598
RAW_DIR = Path("data/trebolares/raw")
PROC_DIR = Path("data/trebolares/processed")


def _load_climate_daily() -> pd.DataFrame:
    path = RAW_DIR / "climate_daily.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró {path}. Corré primero scripts/01_fetch_climate.py"
        )
    return pd.read_parquet(path)


def _end_year(daily: pd.DataFrame) -> int:
    return int(daily["date"].dt.year.max())


def main() -> None:
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    print("Cargando serie climática diaria...")
    daily = _load_climate_daily()
    start_year = MIN_NASA_YEAR
    end_year = _end_year(daily)
    print(f"  {len(daily):,} días  ({start_year}–{end_year})\n")

    scenarios = list_active_crop_scenarios()
    for scenario in scenarios:
        print(f"Calculando {scenario.label}...")
        try:
            result = run_crop_agro_analysis(
                climate_daily=daily,
                latitude_deg=LAT,
                crop=scenario,
                start_campaign_year=start_year,
                end_campaign_year=end_year,
            )
        except Exception as exc:
            print(f"  ✗ Error: {exc}")
            continue

        # ── Save DataFrames ────────────────────────────────────────────────
        base = PROC_DIR / f"agro_{scenario.key}"

        cd = result["campaign_daily"].copy()
        # Drop object columns that don't serialise cleanly to parquet
        obj_cols = [c for c in cd.columns if cd[c].dtype == object and c not in
                    ("campaign_label", "stage_key", "stage_label",
                     "campaign_class", "eto_method", "eto_method_label",
                     "eto_method_note", "score_driver", "interpretation")]
        cd = cd.drop(columns=obj_cols, errors="ignore")
        cd.to_parquet(f"{base}_campaign_daily.parquet", index=False)

        result["campaign_summary"].to_parquet(
            f"{base}_campaign_summary.parquet", index=False
        )
        result["stage_summary"].to_parquet(
            f"{base}_stage_summary.parquet", index=False
        )

        # ── Save metadata ──────────────────────────────────────────────────
        meta = {
            "scenario_key": scenario.key,
            "scenario_label": scenario.label,
            "global_summary": result["global_summary"],
            "eto_method": result["eto_method"],
            "eto_method_label": result["eto_method_label"],
            "eto_method_note": result["eto_method_note"],
            "methodology_notes": result["methodology_notes"],
        }
        with open(f"{base}_meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        n_campaigns = len(result["campaign_summary"])
        mean_score = result["global_summary"]["mean_score"]
        band = result["global_summary"]["score_band"]
        print(f"  ✓ {n_campaigns} campañas  |  score medio {mean_score:.1f}  |  {band}")

    print("\nDone.")


if __name__ == "__main__":
    main()
