"""Data store — loads pre-computed Trebolares data from disk.

All public functions are decorated with @st.cache_data so Streamlit only
reads from disk once per session.  Scripts and notebooks can import the
same functions; the cache decorator is a no-op outside a Streamlit context.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.climate import compute_agroclimatic_indicators
from src.crops import get_crop_scenario, list_active_crop_scenarios

_PROC = Path("data/trebolares/processed")
_RAW = Path("data/trebolares/raw")

SCENARIOS = [s.key for s in list_active_crop_scenarios()]


# ─── Readiness check ──────────────────────────────────────────────────────────

def data_ready() -> bool:
    """Return True when all expected processed files exist."""
    required = [
        _RAW / "climate_daily.parquet",
        _PROC / "climate_annual.parquet",
        _PROC / "climate_monthly_by_year.parquet",
        _PROC / "climate_monthly_climatology.parquet",
        _PROC / "soil.json",
        _PROC / "terrain.json",
    ] + [
        _PROC / f"agro_{key}_campaign_summary.parquet"
        for key in SCENARIOS
    ]
    return all(p.exists() for p in required)


# ─── Climate ──────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_climate_bundle() -> dict[str, Any]:
    """Load the full climate bundle from pre-computed files."""
    from src.config import MONTH_LABELS

    daily = pd.read_parquet(_RAW / "climate_daily.parquet")
    annual = pd.read_parquet(_PROC / "climate_annual.parquet")
    monthly_by_year = pd.read_parquet(_PROC / "climate_monthly_by_year.parquet")
    mc = pd.read_parquet(_PROC / "climate_monthly_climatology.parquet")

    # Restore ordered Categorical on month_label
    mc["month_label"] = pd.Categorical(
        mc["month_label"], categories=MONTH_LABELS, ordered=True
    )

    indicators_path = _PROC / "climate_indicators.json"
    if indicators_path.exists():
        with open(indicators_path, encoding="utf-8") as f:
            indicators = json.load(f)
    else:
        indicators = dict(compute_agroclimatic_indicators(annual, mc))

    return {
        "daily": daily,
        "annual": annual,
        "monthly_by_year": monthly_by_year,
        "monthly_climatology": mc,
        "indicators": indicators,
    }


# ─── Soil & terrain ───────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_soil() -> dict[str, Any]:
    with open(_PROC / "soil.json", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_terrain() -> dict[str, Any]:
    with open(_PROC / "terrain.json", encoding="utf-8") as f:
        return json.load(f)


# ─── Agroclimatic analysis ────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_agro(scenario_key: str) -> dict[str, Any]:
    """Reconstruct an AgroAnalysisResult from pre-computed files."""
    crop = get_crop_scenario(scenario_key)
    base = _PROC / f"agro_{scenario_key}"

    campaign_daily = pd.read_parquet(f"{base}_campaign_daily.parquet")
    campaign_summary = pd.read_parquet(f"{base}_campaign_summary.parquet")
    stage_summary = pd.read_parquet(f"{base}_stage_summary.parquet")

    with open(f"{base}_meta.json", encoding="utf-8") as f:
        meta = json.load(f)

    return {
        "crop": crop,
        "scenario": crop,
        "campaign_daily": campaign_daily,
        "campaign_summary": campaign_summary,
        "stage_summary": stage_summary,
        "global_summary": meta["global_summary"],
        "eto_method": meta["eto_method"],
        "eto_method_label": meta["eto_method_label"],
        "eto_method_note": meta["eto_method_note"],
        "methodology_notes": meta["methodology_notes"],
    }


@st.cache_data(show_spinner=False)
def load_all_agro() -> dict[str, Any]:
    """Load all active scenario analyses in one call."""
    return {key: load_agro(key) for key in SCENARIOS}
