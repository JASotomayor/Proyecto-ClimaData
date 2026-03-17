"""Fetch soil (SoilGrids) and terrain (OpenTopoData) for Campo Trebolares.

Run once from the project root:
    python scripts/02_fetch_soil_terrain.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.soil import get_soil_summary
from src.terrain import get_terrain_summary
from src.utils import GeoPoint

LAT = -35.5598
LON = -63.5924
POINT = GeoPoint(lat=LAT, lon=LON, source="farm_kml", label="Centroide Trebolares")

PROC_DIR = Path("data/trebolares/processed")


def _jsonable(obj: object) -> object:
    """Recursively convert non-JSON-serializable types."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "__float__"):
        return float(obj)  # numpy floats, etc.
    return obj


def main() -> None:
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching soil summary (SoilGrids)...")
    soil = get_soil_summary(POINT)
    soil_path = PROC_DIR / "soil.json"
    with open(soil_path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(dict(soil)), f, ensure_ascii=False, indent=2)
    status = "available" if soil.get("available") else f"unavailable — {soil.get('error')}"
    print(f"  ✓ {status}  →  {soil_path}")

    print("Fetching terrain summary (OpenTopoData)...")
    terrain = get_terrain_summary(POINT)
    terrain_path = PROC_DIR / "terrain.json"
    with open(terrain_path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(dict(terrain)), f, ensure_ascii=False, indent=2)
    status = "available" if terrain.get("available") else f"unavailable — {terrain.get('error')}"
    print(f"  ✓ {status}  →  {terrain_path}")

    print("Done.\n")


if __name__ == "__main__":
    main()
