"""Climate dashboard tab for the Trebolares Streamlit app.

Renders historical climate analysis from pre-computed NASA POWER data.
All charts use Plotly for consistency with the rest of the UI.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ─── Design tokens ────────────────────────────────────────────────────────────
_NAVY       = "#1E3953"
_BLUE       = "#607E93"
_BLUE_LIGHT = "#8FA8BB"
_ORANGE     = "#EF9645"
_GRAY_LIGHT = "#F7F6F5"
_GRAY_WARM  = "#D8D4D0"
_WHITE      = "#FFFFFF"
_GREEN      = "#3A7D44"
_RED        = "#BF4040"

_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_family="Montserrat, sans-serif",
    font_color=_NAVY,
    margin=dict(l=8, r=8, t=28, b=36),
    dragmode=False,
)

_CLIMA_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
    "staticPlot": True,
}


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


# ─── Section: Indicators header ───────────────────────────────────────────────

def _render_indicators(indicators: dict[str, Any]) -> None:
    """Compact KPI row from agroclimatic indicators."""
    precip    = indicators.get("annual_precip_mean", 0)
    temp      = indicators.get("annual_temp_mean", 0)
    cv        = indicators.get("rainfall_cv", 0)
    stability = indicators.get("water_stability", "—")
    drought   = indicators.get("drought_risk", "—")
    frost     = indicators.get("frost_risk", "—")
    wettest   = indicators.get("wettest_year", {})
    driest    = indicators.get("driest_year", {})
    seasonality = indicators.get("rainfall_seasonality", "—")
    frost_months = indicators.get("frost_months", [])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Precip. media anual", f"{precip:.0f} mm")
    c2.metric("Temp. media anual",   f"{temp:.1f} °C")
    c3.metric("CV precipitación",    f"{cv:.0f}%")
    c4.metric("Estabilidad hídrica", stability)
    c5.metric("Riesgo sequía",       drought)
    c6.metric("Riesgo helada",       frost)

    st.caption(
        f"Año más lluvioso: {wettest.get('year','—')} ({wettest.get('value',0):.0f} mm)  ·  "
        f"Año más seco: {driest.get('year','—')} ({driest.get('value',0):.0f} mm)  ·  "
        f"Estacionalidad: {seasonality}  ·  "
        f"Meses con riesgo de helada: {', '.join(frost_months) if frost_months else 'ninguno'}"
    )


# ─── Section: Annual precipitation ───────────────────────────────────────────

def _render_annual_precip(annual: pd.DataFrame) -> None:
    _section("Precipitación anual")

    if annual.empty:
        st.info("Sin datos anuales disponibles.")
        return

    mean_val = float(annual["precipitation_mm"].mean())
    colors = [
        _GREEN if v >= mean_val * 1.15 else (_RED if v <= mean_val * 0.85 else _BLUE_LIGHT)
        for v in annual["precipitation_mm"]
    ]

    fig = go.Figure()
    border_colors = [
        "#2D5F35" if v >= mean_val * 1.15 else ("#8B2020" if v <= mean_val * 0.85 else _BLUE)
        for v in annual["precipitation_mm"]
    ]
    fig.add_trace(go.Bar(
        x=annual["year"],
        y=annual["precipitation_mm"].round(0),
        marker_color=colors,
        marker_line_color=border_colors,
        marker_line_width=1,
        hovertemplate="%{x}: %{y:.0f} mm<extra></extra>",
        name="Precipitación",
    ))
    fig.add_hline(
        y=mean_val,
        line_dash="dot",
        line_color=_NAVY,
        line_width=1.5,
        annotation_text=f"Media {mean_val:.0f} mm",
        annotation_position="top right",
        annotation_font_size=9,
        annotation_font_color=_NAVY,
    )
    fig.update_layout(
        **_PLOTLY_BASE,
        height=280,
        showlegend=False,
        xaxis=dict(tickfont_size=9, dtick=2),
        yaxis=dict(title="mm", tickfont_size=9),
        bargap=0.25,
    )
    st.plotly_chart(fig, use_container_width=True, config=_CLIMA_CONFIG)

    # Anomaly strip
    fig2 = go.Figure()
    anom = annual["precipitation_anomaly_pct"]
    bar_colors = [_GREEN if v >= 0 else _RED for v in anom]
    border_colors2 = ["#2D5F35" if v >= 0 else "#8B2020" for v in anom]
    fig2.add_trace(go.Bar(
        x=annual["year"],
        y=anom.round(1),
        marker_color=bar_colors,
        marker_line_color=border_colors2,
        marker_line_width=1,
        hovertemplate="%{x}: %{y:+.1f}%<extra></extra>",
    ))
    fig2.add_hline(y=0, line_color=_NAVY, line_width=1)
    fig2.update_layout(
        **{**_PLOTLY_BASE, "margin": dict(l=8, r=8, t=36, b=36)},
        height=180,
        showlegend=False,
        title_text="Anomalía respecto a la media (%)",
        title_font_size=10,
        xaxis=dict(tickfont_size=9, dtick=2),
        yaxis=dict(title="%", tickfont_size=9),
        bargap=0.25,
    )
    st.plotly_chart(fig2, use_container_width=True, config=_CLIMA_CONFIG)


# ─── Section: Monthly climatology ─────────────────────────────────────────────

def _render_monthly_climatology(mc: pd.DataFrame) -> None:
    _section("Climatología mensual (media histórica)")

    if mc.empty:
        st.info("Sin climatología mensual disponible.")
        return

    mc_sorted = mc.sort_values("month")
    month_labels = mc_sorted["month_label"].astype(str).tolist()

    # Precipitation bars + temperature lines (dual axis)
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=month_labels,
        y=mc_sorted["precipitation_mm"].round(1),
        name="Precipitación (mm)",
        marker_color=_BLUE_LIGHT,
        marker_line_color=_BLUE,
        marker_line_width=1,
        yaxis="y",
        hovertemplate="%{x}: %{y:.1f} mm<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=month_labels,
        y=mc_sorted["temp_max_c"].round(1),
        name="Tmax",
        mode="lines+markers",
        line=dict(color=_RED, width=2),
        marker=dict(size=5),
        yaxis="y2",
        hovertemplate="%{x} Tmax: %{y:.1f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=month_labels,
        y=mc_sorted["temp_mean_c"].round(1),
        name="Tmean",
        mode="lines+markers",
        line=dict(color=_ORANGE, width=2, dash="dot"),
        marker=dict(size=5),
        yaxis="y2",
        hovertemplate="%{x} Tmean: %{y:.1f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=month_labels,
        y=mc_sorted["temp_min_c"].round(1),
        name="Tmin",
        mode="lines+markers",
        line=dict(color=_BLUE, width=2),
        marker=dict(size=5),
        yaxis="y2",
        hovertemplate="%{x} Tmin: %{y:.1f} °C<extra></extra>",
    ))

    fig.update_layout(
        **_PLOTLY_BASE,
        height=320,
        yaxis=dict(title="Precipitación (mm)", tickfont_size=9, showgrid=True, gridcolor=_GRAY_WARM),
        yaxis2=dict(
            title="Temperatura (°C)",
            overlaying="y",
            side="right",
            tickfont_size=9,
            showgrid=False,
        ),
        legend=dict(orientation="h", y=-0.28, xanchor="center", x=0.5, font_size=9, itemclick=False, itemdoubleclick=False),
        xaxis=dict(tickfont_size=9),
        bargap=0.3,
    )
    st.plotly_chart(fig, use_container_width=True, config=_CLIMA_CONFIG)


# ─── Section: Annual temperature ──────────────────────────────────────────────

def _render_annual_temperature(annual: pd.DataFrame) -> None:
    _section("Temperatura anual")

    if annual.empty:
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=annual["year"],
        y=annual["temp_max_c"].round(2),
        name="Tmax media",
        mode="lines+markers",
        line=dict(color=_RED, width=1.5),
        marker=dict(size=4),
        hovertemplate="%{x} Tmax: %{y:.1f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=annual["year"],
        y=annual["temp_mean_c"].round(2),
        name="Tmean",
        mode="lines+markers",
        line=dict(color=_ORANGE, width=2, dash="dot"),
        marker=dict(size=5),
        hovertemplate="%{x} Tmean: %{y:.1f} °C<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=annual["year"],
        y=annual["temp_min_c"].round(2),
        name="Tmin media",
        mode="lines+markers",
        line=dict(color=_BLUE, width=1.5),
        marker=dict(size=4),
        hovertemplate="%{x} Tmin: %{y:.1f} °C<extra></extra>",
    ))

    fig.update_layout(
        **_PLOTLY_BASE,
        height=260,
        xaxis=dict(tickfont_size=9, dtick=2),
        yaxis=dict(title="°C", tickfont_size=9),
        legend=dict(orientation="h", y=-0.28, xanchor="center", x=0.5, font_size=9, itemclick=False, itemdoubleclick=False),
    )
    st.plotly_chart(fig, use_container_width=True, config=_CLIMA_CONFIG)


# ─── Section: Monthly precipitation variability ───────────────────────────────

def _render_monthly_variability(monthly_by_year: pd.DataFrame) -> None:
    _section("Variabilidad interanual de la precipitación mensual")

    if monthly_by_year.empty:
        return

    mc_sorted = (
        monthly_by_year
        .groupby(["month", "month_label"])["precipitation_mm"]
        .agg(["mean", "std", lambda x: x.quantile(0.25), lambda x: x.quantile(0.75)])
        .reset_index()
    )
    mc_sorted.columns = ["month", "month_label", "mean", "std", "p25", "p75"]
    mc_sorted = mc_sorted.sort_values("month")
    labels = mc_sorted["month_label"].astype(str).tolist()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels,
        y=mc_sorted["mean"].round(1),
        name="Media",
        marker_color=_BLUE_LIGHT,
        marker_line_color=_BLUE,
        marker_line_width=1,
        error_y=dict(
            type="data",
            array=mc_sorted["std"].round(1).tolist(),
            color=_NAVY,
            thickness=1.2,
            width=4,
        ),
        hovertemplate="%{x}: %{y:.1f} mm (±SD)<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=labels,
        y=mc_sorted["p25"].round(1),
        name="P25",
        mode="lines",
        line=dict(color=_ORANGE, width=1.5, dash="dot"),
        hovertemplate="P25: %{y:.1f} mm<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=labels,
        y=mc_sorted["p75"].round(1),
        name="P75",
        mode="lines",
        line=dict(color=_GREEN, width=1.5, dash="dot"),
        hovertemplate="P75: %{y:.1f} mm<extra></extra>",
    ))

    fig.update_layout(
        **_PLOTLY_BASE,
        height=280,
        bargap=0.3,
        xaxis=dict(tickfont_size=9),
        yaxis=dict(title="mm", tickfont_size=9),
        legend=dict(orientation="h", y=-0.28, xanchor="center", x=0.5, font_size=9, itemclick=False, itemdoubleclick=False),
    )
    st.plotly_chart(fig, use_container_width=True, config=_CLIMA_CONFIG)


# ─── Section: Precipitation ranking ──────────────────────────────────────────

def _render_precip_ranking(annual: pd.DataFrame) -> None:
    _section("Ranking de años por precipitación")

    if annual.empty:
        return

    ranked = annual.sort_values("precipitation_mm", ascending=True).copy()
    mean_val = float(annual["precipitation_mm"].mean())
    bar_colors = [
        _GREEN if v >= mean_val * 1.15 else (_RED if v <= mean_val * 0.85 else _BLUE_LIGHT)
        for v in ranked["precipitation_mm"]
    ]

    fig = go.Figure()
    border_colors3 = [
        "#2D5F35" if v >= mean_val * 1.15 else ("#8B2020" if v <= mean_val * 0.85 else _BLUE)
        for v in ranked["precipitation_mm"]
    ]
    fig.add_trace(go.Bar(
        x=ranked["precipitation_mm"].round(0),
        y=ranked["year"].astype(str),
        orientation="h",
        marker_color=bar_colors,
        marker_line_color=border_colors3,
        marker_line_width=1,
        hovertemplate="%{y}: %{x:.0f} mm<extra></extra>",
    ))
    fig.add_vline(
        x=mean_val,
        line_dash="dot",
        line_color=_NAVY,
        line_width=1.5,
        annotation_text=f"Media {mean_val:.0f} mm",
        annotation_position="top right",
        annotation_font_size=9,
    )
    fig.update_layout(
        **{**_PLOTLY_BASE, "margin": dict(l=48, r=8, t=28, b=36)},
        height=max(300, len(ranked) * 18),
        showlegend=False,
        xaxis=dict(title="mm", tickfont_size=9),
        yaxis=dict(tickfont_size=8),
    )
    st.plotly_chart(fig, use_container_width=True, config=_CLIMA_CONFIG)


# ─── Public entry point ───────────────────────────────────────────────────────

def render_climate_tab(climate_bundle: dict[str, Any]) -> None:
    """Render the full climate dashboard inside the current Streamlit tab."""
    daily       = climate_bundle.get("daily", pd.DataFrame())
    annual      = climate_bundle.get("annual", pd.DataFrame())
    monthly_by_year = climate_bundle.get("monthly_by_year", pd.DataFrame())
    mc          = climate_bundle.get("monthly_climatology", pd.DataFrame())
    indicators  = climate_bundle.get("indicators", {})

    if annual.empty:
        st.error("No hay datos climáticos disponibles. Corré scripts/01_fetch_climate.py.")
        return

    years = f"{int(annual['year'].min())}–{int(annual['year'].max())}"
    st.caption(
        f"NASA POWER ERA5-reanalysis · resolución ~55 km · {years} · "
        f"{len(annual)} años · {len(daily):,} días de serie diaria"
    )

    _render_indicators(indicators)
    st.divider()

    col_left, col_right = st.columns([3, 2])
    with col_left:
        _render_annual_precip(annual)
    with col_right:
        _render_precip_ranking(annual)

    st.divider()
    _render_monthly_climatology(mc)

    st.divider()
    col2a, col2b = st.columns([2, 3])
    with col2a:
        _render_annual_temperature(annual)
    with col2b:
        _render_monthly_variability(monthly_by_year)

    # Agroclimatic insights
    if indicators:
        st.divider()
        _section("Lectura agroclimatológica")
        cv   = indicators.get("rainfall_cv", 0)
        stab = indicators.get("water_stability", "")
        drought = indicators.get("drought_risk", "")
        frost_months = indicators.get("frost_months", [])
        seasonality  = indicators.get("rainfall_seasonality", "")

        _insight(
            f"<b>Variabilidad interanual de la precipitación: CV {cv:.0f}% — {stab}.</b> "
            f"CV calculado sobre la serie completa ({years}). "
            f"Por encima del 25% la dispersión interanual es alta y el resultado de campaña "
            f"depende significativamente del año; por debajo del 20% la oferta hídrica es más predecible."
        )
        _insight(
            f"<b>Estacionalidad pluviométrica: {seasonality}.</b> "
            "La concentración estacional de las lluvias determina en qué etapas fenológicas "
            "cae el grueso de la precipitación. Una estacionalidad marcada en verano favorece "
            "maíz y soja pero puede dejar a trigo con una fase de llenado seca."
        )
        if frost_months:
            frost_str = ", ".join(frost_months)
            _insight(
                f"<b>Riesgo de helada por Tmin media mensual: {frost_str}.</b> "
                "La temperatura mínima media mensual es un indicador conservador; "
                "los años con anomalía negativa pueden extender el riesgo hacia meses adyacentes. "
                "El umbral crítico de daño varía por cultivo y estadio: −2 °C en espigazón de trigo, "
                "0 °C en floración de maíz temprano."
            )
        else:
            _insight(
                "<b>Sin meses con Tmin media ≤ 0 °C en la serie histórica.</b> "
                "El perfil térmico promedio no presenta restricción por helada, aunque "
                "eventos puntuales en años con anomalía negativa no pueden descartarse."
            )
        _insight(
            f"<b>Riesgo de sequía: {drought}.</b> "
            "Estimado a partir del CV interanual y la magnitud del déficit del año más seco "
            f"({indicators.get('driest_year', {}).get('year', '—')}: "
            f"{indicators.get('driest_year', {}).get('value', 0):.0f} mm) "
            "respecto a la media histórica. Contrastar con el balance P–ETc por cultivo "
            "en cada pestaña de escenario."
        )
