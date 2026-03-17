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
    render_sidebar,
)

_NAV_PAGES = ["Finca", "Clima", "Cultivos", "Producción", "Metodología"]


# ─── Navigation ───────────────────────────────────────────────────────────────

def _init_nav() -> None:
    qp_page = st.query_params.get("p", None)
    if qp_page in _NAV_PAGES:
        st.session_state["page"] = qp_page
    elif "page" not in st.session_state:
        st.session_state["page"] = _NAV_PAGES[0]


# ─── Header ───────────────────────────────────────────────────────────────────

def _render_app_header(page: str) -> None:
    st.title(page)
    st.caption("Lote Prime · Inteligencia agronómica para validar escenarios · Campo en Maracó, La Pampa")


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


# ─── Page renderers ───────────────────────────────────────────────────────────

def _page_finca(farm_geometry, climate_bundle, soil_summary, terrain_summary) -> None:
    render_farm_identity_card(
        farm_geometry=farm_geometry,
        point=farm_geometry.centroid,
        soil_summary=soil_summary,
        terrain_summary=terrain_summary,
    )
    render_map_card(farm_geometry.centroid, farm_geometry=farm_geometry)
    render_farm_tab(
        farm_geometry=farm_geometry,
        point=farm_geometry.centroid,
        climate_bundle=climate_bundle,
    )
    st.divider()
    render_ndvi_section(farm_geometry)


def _page_cultivos(
    farm_geometry, climate_bundle, soil_summary, terrain_summary, scenario_analyses
) -> None:
    scenarios = list_active_crop_scenarios()
    scenario_labels = {s.label: s for s in scenarios}
    selected_label = st.radio(
        "Cultivo / escenario",
        list(scenario_labels.keys()),
        key="cultivo_select",
        horizontal=True,
    )
    selected_scenario = scenario_labels[selected_label]
    render_scenario_tab(
        scenario=selected_scenario,
        analysis_result=scenario_analyses.get(selected_scenario.key),
        soil_summary=soil_summary,
        terrain_summary=terrain_summary,
        climate_bundle=climate_bundle,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    initialize_page()
    _init_nav()

    farm_geometry = load_default_farm()
    if farm_geometry is None:
        st.error("No se encontró `data/Trebolares.kml`.")
        return

    # ── Sidebar: brand + nav buttons ──────────────────────────────────────────
    render_sidebar(farm_geometry, start_year=2001, end_year=2024)
    _current_page = st.session_state.get("page", _NAV_PAGES[0])
    with st.sidebar:
        for _p in _NAV_PAGES:
            if st.button(
                _p,
                key=f"_nav_{_p}",
                use_container_width=True,
                type="primary" if _p == _current_page else "secondary",
            ):
                st.session_state["page"] = _p
                st.rerun()

    _render_app_header(_current_page)

    if not data_ready():
        _render_setup_screen()
        return

    climate_bundle = load_climate_bundle()
    soil_summary = load_soil()
    terrain_summary = load_terrain()
    scenario_analyses = load_all_agro()

    page = st.session_state["page"]

    if page == "Finca":
        _page_finca(farm_geometry, climate_bundle, soil_summary, terrain_summary)
    elif page == "Clima":
        render_climate_tab(climate_bundle)
    elif page == "Cultivos":
        _page_cultivos(
            farm_geometry, climate_bundle, soil_summary, terrain_summary, scenario_analyses
        )
    elif page == "Producción":
        render_produccion_tab()
    elif page == "Metodología":
        render_methodology_tab(*get_online_scope_sections())


if __name__ == "__main__":
    main()
