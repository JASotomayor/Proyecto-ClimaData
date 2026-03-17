from __future__ import annotations

import streamlit as st

from src.crops import list_active_crop_scenarios
from src.data_store import (
    data_ready,
    load_all_agro,
    load_climate_bundle,
    load_soil,
    load_terrain,
)
from src.farm import load_default_farm
from src.climate_dashboard import render_climate_tab
from src.produccion_dashboard import render_produccion_tab
from src.farm_dashboard import render_farm_identity_card
from src.raster_map import render_ndvi_section
from src.reporting import get_online_scope_sections
from src.scenario_dashboard import render_scenario_tab
from src.ui import (
    initialize_page,
    render_farm_tab,
    render_map_card,
    render_methodology_tab,
    render_mobile_topbar,
    render_sidebar,
)


# ─── Header ───────────────────────────────────────────────────────────────────

def _render_app_header() -> None:
    st.title("Diagnóstico de finca")
    st.caption("Campo en Trebolares · análisis agronómico histórico 2001–presente.")


# ─── Setup screen ─────────────────────────────────────────────────────────────

def _render_setup_screen() -> None:
    st.warning(
        "Los datos procesados aún no están disponibles. "
        "Corré los scripts de extracción desde la terminal:"
    )
    st.code(
        "python scripts/01_fetch_climate.py\n"
        "python scripts/02_fetch_soil_terrain.py\n"
        "python scripts/03_compute_agro.py",
        language="bash",
    )


# ─── Tab layout ───────────────────────────────────────────────────────────────

def _render_tabs(farm_geometry, climate_bundle, soil_summary, terrain_summary, scenario_analyses):
    scenarios = list_active_crop_scenarios()
    tab_labels = ["Finca", "Clima", "Cultivos", "Producción", "Metodología"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        render_map_card(farm_geometry.centroid, farm_geometry=farm_geometry)
        render_farm_identity_card(
            farm_geometry=farm_geometry,
            point=farm_geometry.centroid,
            soil_summary=soil_summary,
            terrain_summary=terrain_summary,
        )
        st.divider()
        render_ndvi_section(farm_geometry)
        st.divider()
        render_farm_tab(
            farm_geometry=farm_geometry,
            point=farm_geometry.centroid,
            climate_bundle=climate_bundle,
        )

    with tabs[1]:
        render_climate_tab(climate_bundle)

    with tabs[2]:
        scenario_labels = {s.label: s for s in scenarios}
        selected_label = st.selectbox(
            "Cultivo / escenario",
            list(scenario_labels.keys()),
            key="cultivo_select",
        )
        selected_scenario = scenario_labels[selected_label]
        render_scenario_tab(
            scenario=selected_scenario,
            analysis_result=scenario_analyses.get(selected_scenario.key),
            soil_summary=soil_summary,
            terrain_summary=terrain_summary,
            climate_bundle=climate_bundle,
        )

    with tabs[3]:
        render_produccion_tab()

    with tabs[4]:
        render_methodology_tab(*get_online_scope_sections())


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    initialize_page()

    farm_geometry = load_default_farm()
    if farm_geometry is None:
        st.error("No se encontró `data/Trebolares.kml`.")
        return

    from src.config import MIN_NASA_YEAR, MAX_COMPLETE_YEAR
    render_sidebar(farm_geometry, MIN_NASA_YEAR, MAX_COMPLETE_YEAR)
    render_mobile_topbar(farm_geometry, MIN_NASA_YEAR, MAX_COMPLETE_YEAR)
    _render_app_header()

    if not data_ready():
        _render_setup_screen()
        return

    climate_bundle = load_climate_bundle()
    soil_summary = load_soil()
    terrain_summary = load_terrain()
    scenario_analyses = load_all_agro()

    _render_tabs(farm_geometry, climate_bundle, soil_summary, terrain_summary, scenario_analyses)


if __name__ == "__main__":
    main()
