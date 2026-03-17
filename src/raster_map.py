"""Render the NDVI raster map inside the Finca tab.

Presents the multianual NDVI median from ``src.satellite`` as a smooth
continuous raster clipped to the farm polygon — red → yellow → green
palette with a colorbar and polygon border overlay.
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.satellite import fetch_ndvi_median

# ─── Design tokens ────────────────────────────────────────────────────────────
_NAVY       = "#1E3953"
_BLUE_LIGHT = "#8FA8BB"
_GRAY_WARM  = "#D8D4D0"

_CHART_CFG  = {"displayModeBar": False, "scrollZoom": False, "staticPlot": True}

_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    font_family="Montserrat, sans-serif",
    font_color=_NAVY,
    dragmode=False,
)

# ─── Internal helpers ─────────────────────────────────────────────────────────

def _aspect_ratio(lats: np.ndarray) -> float:
    """Correction factor lon_deg / lat_deg at the mean latitude."""
    mean_lat = float(np.mean(lats))
    return 1.0 / max(math.cos(math.radians(abs(mean_lat))), 0.01)


def _normalize_p2_p98(arr: np.ndarray) -> np.ndarray:
    """Stretch to [0, 1] using the P2–P98 range; clip extremes."""
    valid = arr[~np.isnan(arr)]
    if len(valid) < 10:
        return np.zeros_like(arr)
    p2, p98 = np.percentile(valid, 2), np.percentile(valid, 98)
    rng = p98 - p2
    if rng < 1e-6:
        return np.full_like(arr, 0.5)
    return np.clip((arr - p2) / rng, 0.0, 1.0)


# ─── Section entry point ──────────────────────────────────────────────────────

def render_ndvi_section(
    farm_geometry,
    start_year: int = 2018,
    end_year: int = 2024,
) -> None:
    """Render the full NDVI raster section (title + map + caption + notes).

    Fetches data on first call (cached for the session); subsequent
    calls are instant.  Shows a spinner while computing.
    """
    st.markdown(
        '<span class="ms-section-header">Variabilidad espacial · Potencial relativo</span>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Mediana NDVI Sentinel-2 L2A · temporadas noviembre–marzo "
        f"{start_year}–{end_year} · resolución 10 m · recortado al polígono KML."
    )

    with st.spinner("Descargando imágenes Sentinel-2 y calculando NDVI…"):
        result = fetch_ndvi_median(
            coordinates=farm_geometry.coordinates,
            bbox=farm_geometry.bbox,
            start_year=start_year,
            end_year=end_year,
        )

    if result.get("error"):
        st.warning(f"Mapa no disponible: {result['error']}")
        return

    _render_heatmap(farm_geometry, result, start_year, end_year)


# ─── Heatmap figure ───────────────────────────────────────────────────────────

def _render_heatmap(
    farm_geometry,
    result: dict,
    start_year: int,
    end_year: int,
) -> None:
    arr      = result["ndvi"]         # 2D float32, row-0 = southernmost
    lats     = result["lats"]         # 1D increasing S→N
    lons     = result["lons"]         # 1D increasing W→E
    n_scenes = result.get("n_scenes", 0)

    arr_norm = _normalize_p2_p98(arr)

    # Polygon border (close the ring)
    poly_lons = [c[0] for c in farm_geometry.coordinates]
    poly_lats = [c[1] for c in farm_geometry.coordinates]
    poly_lons.append(poly_lons[0])
    poly_lats.append(poly_lats[0])

    aspect = _aspect_ratio(lats)

    # ── Figure height: proportional to field aspect, clamped ──────────────
    lat_span = float(max(lats) - min(lats))
    lon_span = float(max(lons) - min(lons))
    if lat_span > 0 and lon_span > 0:
        fig_h = int(np.clip(lon_span / aspect / lat_span * 420, 280, 540))
    else:
        fig_h = 380

    fig = go.Figure()

    # ── Heatmap (NDVI raster) ──────────────────────────────────────────────
    fig.add_trace(go.Heatmap(
        z=arr_norm,
        x=lons,
        y=lats,
        colorscale="RdYlGn",
        zmin=0.0,
        zmax=1.0,
        zsmooth="best",            # bicubic interpolation → smooth raster look
        showscale=True,
        colorbar=dict(
            title=dict(
                text="Potencial relativo",
                font=dict(size=10, color=_NAVY),
                side="right",
            ),
            tickvals=[0.0, 0.5, 1.0],
            ticktext=["Bajo", "Medio", "Alto"],
            tickfont=dict(size=10, color=_NAVY),
            thickness=14,
            len=0.72,
            x=1.01,
            bgcolor="rgba(255,255,255,0.85)",
            borderwidth=0,
        ),
        hovertemplate=(
            "Lon %{x:.5f}<br>Lat %{y:.5f}<br>"
            "Potencial: %{z:.2f}<extra></extra>"
        ),
    ))

    # ── Polygon border (white, 2 px) ───────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=poly_lons,
        y=poly_lats,
        mode="lines",
        line=dict(color="white", width=2),
        showlegend=False,
        hoverinfo="skip",
    ))

    # ── Layout ────────────────────────────────────────────────────────────
    fig.update_layout(
        **_PLOTLY_BASE,
        height=fig_h,
        plot_bgcolor="#1A2433",   # dark background for masked (NaN) cells
        margin=dict(l=0, r=70, t=8, b=8),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=8, color=_BLUE_LIGHT),
            scaleanchor="y",
            scaleratio=aspect,    # preserve geographic proportions
            tickformat=".4f",
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=8, color=_BLUE_LIGHT),
            tickformat=".4f",
        ),
    )

    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG)

    st.caption(
        f"{n_scenes} escenas · nubosidad &lt; 20% · P2–P98 normalizado. "
        "Las celdas fuera del polígono no se muestran (NaN). "
        "El índice expresa potencial relativo dentro del lote, no NDVI absoluto."
    )

    # ── Agronomic note ─────────────────────────────────────────────────────
    st.markdown(
        '<div class="ms-insight">'
        "Las zonas verdes concentran la mayor biomasa activa histórica: mayor "
        "fertilidad de suelo, mejor retención hídrica o posición topográfica "
        "favorable. Las zonas rojas señalan sectores con limitantes persistentes "
        "— suelo, drenaje o relieve — que se mantienen año tras año independientemente "
        "del clima. Esta variabilidad es la base para definir ambientes de manejo."
        "</div>",
        unsafe_allow_html=True,
    )
