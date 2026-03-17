"""Farm identity card rendered at the top of the Finca tab.

This module consolidates the farm's physical identity — geometry, soil,
and terrain — into a compact, mobile-friendly view that answers
"¿qué campo es este?" before any agronomic analysis begins.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from src.farm import FarmGeometry
from src.utils import GeoPoint, format_lat_lon

# ─── Design tokens (mirrored from custom.css) ─────────────────────────────────
_NAVY       = "#1E3953"
_BLUE       = "#607E93"
_BLUE_LIGHT = "#8FA8BB"
_ORANGE     = "#EF9645"
_GRAY_LIGHT = "#F7F6F5"
_GRAY_WARM  = "#D8D4D0"


def _section(label: str) -> None:
    st.markdown(
        f'<span class="ms-section-header">{label}</span>',
        unsafe_allow_html=True,
    )


def _insight(text: str) -> None:
    st.markdown(
        f'<div class="ms-insight">{text}</div>',
        unsafe_allow_html=True,
    )


# ─── Soil identity block ──────────────────────────────────────────────────────

def _soil_identity_lines(soil_summary: dict[str, Any]) -> list[str]:
    """Extract the most agronomically relevant soil descriptors."""
    lines: list[str] = []

    texture = soil_summary.get("texture_class", "")
    if texture:
        lines.append(f"Textura estimada: <b>{texture}</b>")

    ph = soil_summary.get("ph")
    if ph is not None:
        if ph < 5.5:
            ph_note = "ácido — puede limitar disponibilidad de nutrientes"
        elif ph < 6.5:
            ph_note = "moderadamente ácido — dentro del rango tolerable para extensivos"
        elif ph <= 7.5:
            ph_note = "neutro a ligeramente alcalino — rango óptimo general"
        else:
            ph_note = "alcalino — puede condicionar micronutrientes"
        lines.append(f"pH superficial estimado: <b>{ph:.1f}</b> ({ph_note})")

    oc = soil_summary.get("organic_carbon")
    if oc is not None:
        if oc < 1.0:
            oc_note = "bajo — suelo con menor resiliencia a déficits"
        elif oc < 2.5:
            oc_note = "medio"
        else:
            oc_note = "alto — mayor capacidad de retención y buffer térmico"
        lines.append(f"Carbono orgánico estimado: <b>{oc:.1f}%</b> ({oc_note})")

    observations = soil_summary.get("observations", [])
    if observations:
        lines.append(observations[0])

    return lines


# ─── Terrain identity block ───────────────────────────────────────────────────

def _terrain_identity_lines(terrain_summary: dict[str, Any]) -> list[str]:
    """Extract terrain descriptors relevant to field management."""
    lines: list[str] = []

    elev = terrain_summary.get("elevation_m")
    if elev is not None:
        lines.append(f"Elevación estimada: <b>{elev:.0f} m s.n.m.</b>")

    relief = terrain_summary.get("relief_class", "")
    if relief:
        lines.append(f"Relieve local: <b>{relief}</b>")

    drainage = terrain_summary.get("drainage_risk", "")
    if drainage:
        if drainage.lower() == "bajo":
            drn_note = "perfil posicionado en loma o plano con buen escurrimiento relativo"
        elif drainage.lower() == "moderado":
            drn_note = "posición media — atención a años con excesos hídricos"
        else:
            drn_note = "posición baja — riesgo de acumulación de agua en años húmedos"
        lines.append(
            f"Riesgo de acumulación de agua: <b>{drainage}</b> ({drn_note})"
        )

    return lines


# ─── Contextual agronomic notes ───────────────────────────────────────────────

def _soil_terrain_agronomic_notes(
    soil_summary: dict[str, Any] | None,
    terrain_summary: dict[str, Any] | None,
) -> list[str]:
    """Generate 1–3 agronomic notes that connect soil + terrain."""
    notes: list[str] = []

    # Soil texture → water retention context
    if soil_summary and soil_summary.get("available"):
        texture = soil_summary.get("texture_class", "").lower()
        sand = soil_summary.get("sand_pct")
        clay = soil_summary.get("clay_pct")

        if sand is not None and sand > 60:
            notes.append(
                "Suelo con fracción arenosa dominante: menor capacidad de retención hídrica. "
                "Los déficits en etapas críticas se expresan con mayor rapidez."
            )
        elif clay is not None and clay > 45:
            notes.append(
                "Suelo con fracción arcillosa elevada: buena retención hídrica pero mayor "
                "riesgo de anegamiento transitorio en posiciones bajas con excesos."
            )
        elif "franca" in texture or "franco" in texture:
            notes.append(
                "Textura franca: buen balance entre retención y drenaje. "
                "Modera parcialmente los déficits hídricos en etapas críticas."
            )
        # (no match = silty or unclassified — no note added)

    # Terrain drainage → flood/drought interaction
    if terrain_summary and terrain_summary.get("available"):
        drainage = terrain_summary.get("drainage_risk", "").lower()
        if drainage == "alto":
            notes.append(
                "Posición topográfica baja: en años húmedos puede haber excesos que comprometan "
                "la implantación o la sanidad radicular. Validar en campo."
            )
        elif drainage == "moderado":
            notes.append(
                "Posición topográfica intermedia: el comportamiento hídrico puede variar según "
                "el año. La heterogeneidad interna del lote puede ser relevante."
            )

    return notes


# ─── Main public function ─────────────────────────────────────────────────────

def render_farm_identity_card(
    farm_geometry: FarmGeometry | None,
    point: GeoPoint,
    soil_summary: dict[str, Any] | None,
    terrain_summary: dict[str, Any] | None,
) -> None:
    """Render the farm identity card at the top of the Finca tab.

    Shows name, area, soil, terrain and agronomic context in a compact,
    mobile-friendly layout. Does not duplicate what ``render_farm_tab``
    shows below; focuses on the "who is this farm" summary.
    """
    # ── Farm header ──────────────────────────────────────────────────────────
    if farm_geometry:
        name  = farm_geometry.name or "Finca sin nombre"
        area  = f"{farm_geometry.area_ha:.1f} ha"
        coord = format_lat_lon(point.lat, point.lon)
        source_label = "Centroide del polígono KML"
    else:
        name  = "Sin KML cargado"
        area  = "—"
        coord = format_lat_lon(point.lat, point.lon)
        source_label = point.source or "manual"

    st.markdown(
        f"""
        <div style="background:{_NAVY};border-radius:12px;padding:1.1rem 1.4rem 0.9rem;margin-bottom:1.1rem">
          <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;
                      letter-spacing:0.1em;color:{_BLUE_LIGHT};margin-bottom:0.25rem">
            Identidad de finca
          </div>
          <div style="font-size:clamp(1rem,4vw,1.35rem);font-weight:700;
                      color:#FFFFFF;margin-bottom:0.15rem">{name}</div>
          <div style="font-size:0.75rem;color:{_BLUE_LIGHT}">
            {area} &nbsp;·&nbsp; {coord} &nbsp;·&nbsp; {source_label}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not farm_geometry:
        st.info(
            "Cargá un KML desde el panel lateral para ver superficie, "
            "polígono y análisis de variabilidad interna del lote."
        )

    # ── Soil + terrain columns ────────────────────────────────────────────
    soil_ok    = bool(soil_summary and soil_summary.get("available"))
    terrain_ok = bool(terrain_summary and terrain_summary.get("available"))

    if not soil_ok and not terrain_ok:
        st.warning(
            "No se pudo recuperar información de suelo ni de relieve. "
            "La identidad física del campo no está disponible en este intento."
        )
        return

    col_soil, col_terrain = st.columns(2)

    with col_soil:
        _section("Suelo")
        if soil_ok:
            for line in _soil_identity_lines(soil_summary):  # type: ignore[arg-type]
                st.markdown(
                    f'<div style="font-size:0.97rem;padding:0.3rem 0;'
                    f'border-bottom:1px solid {_GRAY_WARM};color:{_NAVY}">'
                    f'{line}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Sin datos de suelo disponibles para este intento.")

    with col_terrain:
        _section("Relieve y posición")
        if terrain_ok:
            for line in _terrain_identity_lines(terrain_summary):  # type: ignore[arg-type]
                st.markdown(
                    f'<div style="font-size:0.97rem;padding:0.3rem 0;'
                    f'border-bottom:1px solid {_GRAY_WARM};color:{_NAVY}">'
                    f'{line}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Sin datos de relieve disponibles para este intento.")

    # ── Agronomic context notes ───────────────────────────────────────────
    notes = _soil_terrain_agronomic_notes(soil_summary, terrain_summary)
    if notes:
        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        _section("Contexto agronómico del campo")
        for note in notes:
            _insight(note)
