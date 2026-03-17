"""Fetch regional crop production data from MAGyP (SIIA) for Departamento Maracó, La Pampa.

Source: datos.magyp.gob.ar — Estimaciones Agrícolas por departamento.
Crops:  maíz, trigo, soja de primera, soja de segunda.

Run from the project root:
    python scripts/04_fetch_produccion_regional.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ─── Config ───────────────────────────────────────────────────────────────────
PROVINCIA   = "La Pampa"
DEPARTAMENTO = "Maracó"
PROC_DIR    = Path("data/trebolares/processed")
TIMEOUT     = 30

SOURCES = {
    "maiz": {
        "url": (
            "https://datos.magyp.gob.ar/dataset/514853fc-0a78-4b6f-a42f-8e89eab784c8"
            "/resource/9a6a02f8-ef58-4250-87c2-f639fec502f1/download/maiz-serie-1923-2024.csv"
        ),
        "col_dept":     "departamento",
        "col_prov":     "provincia",
        "col_cultivo":  "cultivo",
        "label":        "Maíz",
        "scenario_key": "maize",
    },
    "trigo": {
        "url": (
            "https://datos.magyp.gob.ar/dataset/10105e94-c560-4b02-b15f-ef3ef764b833"
            "/resource/50f0edcc-4dfc-4afb-b78a-b164601d36ae/download/trigo-serie-1927-2024.csv"
        ),
        "col_dept":     "departamento",
        "col_prov":     "provincia",
        "col_cultivo":  "cultivo",
        "label":        "Trigo",
        "scenario_key": "wheat",
    },
    "soja_1ra": {
        "url": (
            "https://datos.magyp.gob.ar/dataset/8ae4865f-d2f2-45a2-9343-7a4a12728a90"
            "/resource/60a9bb59-c37b-41a0-9ff0-47b94f92cd23/download/soja-1ra-serie-2000-2019.csv"
        ),
        "col_dept":     "departamento_nombre",
        "col_prov":     "provincia_nombre",
        "col_cultivo":  "cultivo_nombre",
        "label":        "Soja de primera",
        "scenario_key": "soy_first",
    },
    "soja_2da": {
        "url": (
            "https://datos.magyp.gob.ar/dataset/8ae4865f-d2f2-45a2-9343-7a4a12728a90"
            "/resource/e03f5a87-2e9c-4042-bdbf-b73f03d45946/download/soja-2da-serie-2000-2019.csv"
        ),
        "col_dept":     "departamento_nombre",
        "col_prov":     "provincia_nombre",
        "col_cultivo":  "cultivo_nombre",
        "label":        "Soja de segunda",
        "scenario_key": "soy_second",
    },
}

OUTPUT_COLUMNS = [
    "cultivo", "anio", "campania",
    "superficie_sembrada_ha", "superficie_cosechada_ha",
    "produccion_tm", "rendimiento_kgxha",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_csv(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), on_bad_lines="skip")


def _normalize(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Filter to Maracó and normalize column names."""
    col_dept    = cfg["col_dept"]
    col_prov    = cfg["col_prov"]
    col_cultivo = cfg["col_cultivo"]

    # Filter province + department (case-insensitive contains)
    mask = (
        df[col_prov].str.lower().str.contains(PROVINCIA.lower(), na=False)
        & df[col_dept].str.lower().str.contains(DEPARTAMENTO.lower(), na=False)
    )
    sub = df[mask].copy()

    if sub.empty:
        return sub

    # Rename to canonical names
    sub = sub.rename(columns={
        col_cultivo: "cultivo",
        col_prov:    "provincia",
        col_dept:    "departamento",
    })
    sub["cultivo"] = cfg["label"]

    # Coerce numerics
    for col in ["superficie_sembrada_ha", "superficie_cosechada_ha",
                "produccion_tm", "rendimiento_kgxha"]:
        if col in sub.columns:
            sub[col] = pd.to_numeric(sub[col], errors="coerce")

    return sub[["cultivo", "anio", "campania",
                "superficie_sembrada_ha", "superficie_cosechada_ha",
                "produccion_tm", "rendimiento_kgxha"]].sort_values("anio")


def _summary(df: pd.DataFrame, label: str) -> dict:
    """Build a compact summary dict for JSON output."""
    if df.empty:
        return {"available": False, "label": label}

    rend = df["rendimiento_kgxha"].dropna()
    return {
        "available":        True,
        "label":            label,
        "years":            int(df["anio"].count()),
        "year_min":         int(df["anio"].min()),
        "year_max":         int(df["anio"].max()),
        "rendimiento_mean": round(float(rend.mean()), 0) if not rend.empty else None,
        "rendimiento_max":  round(float(rend.max()),  0) if not rend.empty else None,
        "rendimiento_min":  round(float(rend.min()),  0) if not rend.empty else None,
        "rendimiento_cv":   round(float(rend.std(ddof=0) / rend.mean() * 100), 1)
                            if len(rend) > 1 else None,
        "best_year":        int(df.loc[df["rendimiento_kgxha"].idxmax(), "anio"])
                            if not rend.empty else None,
        "worst_year":       int(df.loc[df["rendimiento_kgxha"].idxmin(), "anio"])
                            if not rend.empty else None,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    frames: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict] = {}

    for key, cfg in SOURCES.items():
        print(f"Fetching {cfg['label']} ...")
        try:
            raw = _fetch_csv(cfg["url"])
            df  = _normalize(raw, cfg)
            if df.empty:
                print(f"  ! Sin datos para Maracó en {cfg['label']}")
                summaries[cfg["scenario_key"]] = {"available": False, "label": cfg["label"]}
                continue

            frames[cfg["scenario_key"]] = df
            summaries[cfg["scenario_key"]] = _summary(df, cfg["label"])
            s = summaries[cfg["scenario_key"]]
            print(
                f"  OK  {s['years']} campañas ({s['year_min']}–{s['year_max']})  |  "
                f"rend. medio {s['rendimiento_mean']:.0f} kg/ha  |  "
                f"CV {s['rendimiento_cv']:.0f}%"
            )
        except Exception as exc:
            print(f"  ERROR: {exc}")
            summaries[cfg["scenario_key"]] = {"available": False, "label": cfg["label"], "error": str(exc)}

    # ── Save per-crop parquets ─────────────────────────────────────────────
    for sc_key, df in frames.items():
        path = PROC_DIR / f"produccion_{sc_key}.parquet"
        df.to_parquet(path, index=False)
        print(f"  -> {path}")

    # ── Save combined parquet ──────────────────────────────────────────────
    if frames:
        combined = pd.concat(frames.values(), ignore_index=True)
        combined_path = PROC_DIR / "produccion_regional.parquet"
        combined.to_parquet(combined_path, index=False)
        print(f"\nCombinado: {combined_path}  ({len(combined)} filas)")

    # ── Save summary JSON ──────────────────────────────────────────────────
    meta = {
        "source":       "MAGyP — datos.magyp.gob.ar",
        "departamento": DEPARTAMENTO,
        "provincia":    PROVINCIA,
        "crops":        summaries,
    }
    meta_path = PROC_DIR / "produccion_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Meta:      {meta_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
