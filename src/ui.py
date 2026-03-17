from __future__ import annotations

from typing import Any

import folium
import streamlit as st
from streamlit_folium import st_folium

from src.config import APP_ICON, APP_LAYOUT, APP_TITLE, MAP_ZOOM
from src.farm import FarmGeometry
from src.utils import GeoPoint, format_lat_lon, initialize_session_state, load_local_css


def initialize_page() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)
    initialize_session_state()
    load_local_css("assets/custom.css")


def render_mobile_topbar(farm_geometry: FarmGeometry, start_year: int, end_year: int) -> None:
    """Compact info bar shown only on mobile (hidden on desktop via CSS)."""
    name  = farm_geometry.name or "Finca"
    area  = f"{farm_geometry.area_ha:.0f} ha"
    coord = format_lat_lon(farm_geometry.centroid.lat, farm_geometry.centroid.lon)
    period = f"{start_year}–{end_year}"
    st.markdown(
        f"""
        <div class="ms-mobile-topbar">
          <div class="ms-mobile-topbar-name">{name}</div>
          <div class="ms-mobile-topbar-meta">
            {area} &nbsp;·&nbsp; {coord} &nbsp;·&nbsp; {period}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(farm_geometry: FarmGeometry, start_year: int, end_year: int) -> None:
    """Read-only farm info panel."""
    with st.sidebar:
        st.header("Finca")
        st.markdown(f"**{farm_geometry.name}**")
        st.caption(
            f"{farm_geometry.area_ha:.0f} ha · "
            f"{format_lat_lon(farm_geometry.centroid.lat, farm_geometry.centroid.lon)}"
        )
        st.divider()
        st.header("Período de análisis")
        st.markdown(f"**{start_year} – {end_year}**")
        st.caption(
            f"{end_year - start_year + 1} campañas · "
            "NASA POWER desde 2001 hasta el último año completo."
        )


def _build_basemap(point: GeoPoint, farm_geometry: FarmGeometry | None = None) -> folium.Map:
    fmap = folium.Map(
        location=[point.lat, point.lon],
        zoom_start=MAP_ZOOM,
        control_scale=True,
        tiles="CartoDB positron",
    )
    folium.TileLayer("OpenStreetMap", name="OSM").add_to(fmap)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Satélite",
    ).add_to(fmap)
    if farm_geometry:
        polygon_coordinates = [[lat, lon] for lon, lat in farm_geometry.coordinates]
        folium.Polygon(
            locations=polygon_coordinates,
            color="#1E3953",
            weight=2,
            fill=True,
            fill_color="#EF9645",
            fill_opacity=0.12,
            tooltip=f"{farm_geometry.name} · {farm_geometry.area_ha:.0f} ha",
        ).add_to(fmap)
        fmap.fit_bounds(polygon_coordinates)
    folium.CircleMarker(
        location=[point.lat, point.lon],
        radius=4,
        color="#EF9645",
        fill=True,
        fill_color="#EF9645",
        fill_opacity=1.0,
        tooltip=f"Centroide · {format_lat_lon(point.lat, point.lon)}",
    ).add_to(fmap)
    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap


def render_map_card(point: GeoPoint, farm_geometry: FarmGeometry | None = None) -> None:
    """Render the farm polygon map."""
    st_folium(
        _build_basemap(point, farm_geometry=farm_geometry),
        width=None,
        height=300,
        use_container_width=True,
        key="farm_map",
        returned_objects=[],
    )


def render_farm_tab(
    farm_geometry: FarmGeometry | None,
    point: GeoPoint,
    climate_bundle: dict[str, Any] | None = None,
) -> None:
    """Render farm geometry metrics."""
    if not farm_geometry:
        return
    st.markdown(
        '<span class="ms-section-header">Geometría del lote</span>',
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    cols[0].metric("Superficie", f"{farm_geometry.area_ha:.1f} ha")
    cols[1].metric("Perímetro", f"{farm_geometry.perimeter_m:.0f} m")
    cols[2].metric("Vértices KML", str(farm_geometry.point_count))
    cols[3].metric(
        "Bounding box",
        f"{abs(farm_geometry.bbox[3] - farm_geometry.bbox[1]):.3f}° × "
        f"{abs(farm_geometry.bbox[2] - farm_geometry.bbox[0]):.3f}°",
    )
    st.caption(
        f"Centroide operativo: {format_lat_lon(point.lat, point.lon)} · "
        "el análisis climático y agronómico se calcula sobre este punto."
    )


def render_methodology_tab(estimable: list[str], not_confirmable: list[str]) -> None:
    """Render methodological scope and limitations."""
    import pandas as pd

    # ── Fuentes de datos ──────────────────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Fuentes de datos</span>',
        unsafe_allow_html=True,
    )
    sources_df = pd.DataFrame([
        ("NASA POWER", "ERA5-reanalysis", "~55 km", "Clima diario histórico (precipitación, temperatura mín/máx/media)"),
        ("SoilGrids v2.0", "ISRIC", "250 m", "Propiedades de suelo estimadas globalmente (textura, pH, C orgánico, CEC)"),
        ("OpenTopoData", "SRTM", "30 m", "Elevación digital para inferir relieve local y riesgo de drenaje"),
        ("MAGyP/SIIA", "Estimaciones Agrícolas", "Departamento", "Rendimientos y superficie regional (Maracó, La Pampa)"),
    ], columns=["Fuente", "Modelo/Origen", "Resolución", "Uso"])
    st.dataframe(sources_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Modelo agronómico ─────────────────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Modelo agronómico</span>',
        unsafe_allow_html=True,
    )
    notes = [
        "**ETo:** Hargreaves-Samani FAO Paper 56 con factor 0.88 calibrado INTA Anguil (temperatura mín/máx).",
        "**ETc = ETo × Kc** — coeficientes de cultivo FAO Paper 56 tabla 12, por etapa fenológica.",
        "**Balance hídrico:** precipitación bruta − ETc por etapa; calendario fenológico fijo sin almacenaje de suelo.",
        "**Score 0–100:** componentes hídrico ciclo completo + etapas críticas (mayor peso) + térmico + completitud de datos.",
        "El análisis expresa ajuste agronómico relativo histórico. No predice rendimiento absoluto.",
    ]
    for note in notes:
        st.markdown(f"- {note}")

    st.divider()

    # ── Correlación score–rendimiento ─────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Correlación score–rendimiento (Pearson r)</span>',
        unsafe_allow_html=True,
    )
    corr_df = pd.DataFrame([
        ("Maíz temprano",      0.43),
        ("Trigo",              0.52),
        ("Soja de primera",    0.46),
        ("Soja de segunda",    0.39),
    ], columns=["Cultivo", "r"])
    st.dataframe(corr_df, use_container_width=True, hide_index=True)
    st.caption(
        "r ≈ 0.4–0.5 es consistente con un modelo hídrico simplificado sin almacenaje de suelo. "
        "Calculado sobre años con datos comunes MAGyP/SIIA + scores agroclimáticos (Departamento Maracó)."
    )

    st.divider()

    # ── Alcance ───────────────────────────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Alcance: qué se puede y qué no se puede saber desde fuentes abiertas</span>',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Se puede estimar**")
        for item in estimable:
            st.markdown(f"- {item}")
    with col2:
        st.markdown("**No se puede confirmar con precisión solo online**")
        for item in not_confirmable:
            st.markdown(f"- {item}")
