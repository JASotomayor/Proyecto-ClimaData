"""Agronomic scenario dashboard.

Each call to ``render_scenario_tab`` renders a complete, self-contained
dashboard for one crop scenario. The layout is mobile-first: all charts
use ``use_container_width=True``, section headers are rendered via HTML
classes defined in ``assets/custom.css``, and column counts are kept low
to degrade gracefully on narrow screens.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.agro_scores import AgroAnalysisResult, SCORE_THRESHOLDS
from src.crops import CropScenario
from src.reporting import generate_scenario_agronomic_reading
from src.soil_water import render_soil_water_section

# ─── Design tokens mirrored from custom.css for use in Plotly ─────────────────
_NAVY        = "#1E3953"
_BLUE        = "#607E93"
_BLUE_LIGHT  = "#8FA8BB"
_ORANGE      = "#EF9645"
_GRAY_LIGHT  = "#F7F6F5"
_GRAY_WARM   = "#D8D4D0"
_WHITE       = "#FFFFFF"

_FAV_COLOR   = "#3A7D44"
_INT_COLOR   = "#EF9645"
_REST_COLOR  = "#BF4040"
_FAV_BG      = "#D6EFDC"
_INT_BG      = "#FDE8CC"
_REST_BG     = "#F5D5D5"

_CLASS_COLORS: dict[str, str] = {
    "Favorable":  _FAV_COLOR,
    "Intermedia": _INT_COLOR,
    "Restrictiva":_REST_COLOR,
}

_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_family="Montserrat, sans-serif",
    font_color=_NAVY,
    margin=dict(l=8, r=8, t=28, b=36),
)

_MONTHS_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _class_badge(score: float) -> str:
    if score >= SCORE_THRESHOLDS["favorable"]:
        return '<span class="ms-badge ms-badge-favorable">Favorable</span>'
    if score >= SCORE_THRESHOLDS["intermediate"]:
        return '<span class="ms-badge ms-badge-intermedia">Intermedio</span>'
    return '<span class="ms-badge ms-badge-restrictiva">Restrictivo</span>'


def _band_badge(band: str) -> str:
    key = band.lower()
    if key == "favorable":
        return '<span class="ms-badge ms-badge-favorable">Favorable</span>'
    if key == "intermedio":
        return '<span class="ms-badge ms-badge-intermedia">Intermedio</span>'
    return '<span class="ms-badge ms-badge-restrictiva">Restrictivo</span>'


def _section(label: str) -> None:
    st.markdown(f'<span class="ms-section-header">{label}</span>', unsafe_allow_html=True)


def _insight(text: str) -> None:
    st.markdown(f'<div class="ms-insight">{text}</div>', unsafe_allow_html=True)


def _month_label(month: int, day: int) -> str:
    return f"{_MONTHS_ES[month - 1]} {day}"


# ─── Section: Verdict header ──────────────────────────────────────────────────

def _render_verdict_header(
    global_summary: dict[str, Any],
    scenario: CropScenario,
) -> None:
    score     = global_summary["mean_score"]
    fav_pct   = global_summary["favorable_pct"]
    rest_pct  = global_summary["restrictive_pct"]
    camp_count= global_summary["campaign_count"]
    message   = global_summary["executive_message"]
    badge     = _class_badge(score)

    st.markdown(
        f"""
        <div class="ms-verdict-card">
          <div class="ms-verdict-scenario">{scenario.label}</div>
          <div style="display:flex;align-items:baseline;gap:0.5rem;margin-bottom:0.4rem">
            <span class="ms-verdict-score">{score:.0f}</span>
            <span class="ms-verdict-score-unit">/100</span>
            <span style="margin-left:0.3rem">{badge}</span>
          </div>
          <div class="ms-verdict-message">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Score medio", f"{score:.0f}")
    with c2:
        st.metric("Favorables", f"{fav_pct:.0f}%")
    with c3:
        st.metric("Restrictivas", f"{rest_pct:.0f}%")
    with c4:
        st.metric("Campañas", str(camp_count))


# ─── Section: Crop window timeline ────────────────────────────────────────────

def _build_timeline_chart(scenario: CropScenario) -> go.Figure:
    ref_year = 2001
    start = date(ref_year, scenario.campaign_start_month, scenario.campaign_start_day)

    fig = go.Figure()

    for stage in scenario.stages:
        s_start = start + timedelta(days=stage.start_day - 1)
        s_end   = start + timedelta(days=stage.end_day)
        color   = _ORANGE if stage.critical else _BLUE_LIGHT
        border  = _INT_COLOR if stage.critical else _BLUE

        fig.add_trace(go.Bar(
            name=stage.label,
            x=[(s_end - s_start).days],     # width in days
            y=[stage.label],
            base=[(s_start - date(ref_year, 1, 1)).days],
            orientation="h",
            marker_color=color,
            marker_line_color=border,
            marker_line_width=1.5,
            hovertemplate=(
                f"<b>{stage.label}</b><br>"
                f"Días {stage.start_day}–{stage.end_day}<br>"
                f"{'⚠ Etapa crítica' if stage.critical else 'Etapa normal'}"
                "<extra></extra>"
            ),
        ))

    # Add sowing window band
    sow_start = date(ref_year, scenario.sowing_window_start_month, scenario.sowing_window_start_day)
    sow_end   = date(ref_year, scenario.sowing_window_end_month,   scenario.sowing_window_end_day)
    if sow_end < sow_start:
        sow_end = date(ref_year + 1, scenario.sowing_window_end_month, scenario.sowing_window_end_day)

    sow_x0 = (sow_start - date(ref_year, 1, 1)).days
    sow_x1 = (sow_end   - date(ref_year, 1, 1)).days

    fig.add_vrect(
        x0=sow_x0,
        x1=sow_x1,
        fillcolor=_NAVY,
        opacity=0.08,
        line_width=1,
        line_color=_NAVY,
        annotation_text="Ventana siembra",
        annotation_position="top left",
        annotation_font_size=9,
        annotation_font_color=_NAVY,
    )

    # Month tick positions (day-of-year)
    tick_vals = []
    tick_text = []
    for m in range(1, 14):
        yr = ref_year if m <= 12 else ref_year + 1
        mo = m if m <= 12 else m - 12
        try:
            d = date(yr, mo, 1)
            tick_vals.append((d - date(ref_year, 1, 1)).days)
            tick_text.append(_MONTHS_ES[mo - 1])
        except ValueError:
            pass

    fig.update_layout(
        **_PLOTLY_BASE,
        height=max(180, len(scenario.stages) * 38 + 40),
        barmode="overlay",
        showlegend=False,
        xaxis=dict(
            tickmode="array",
            tickvals=tick_vals,
            ticktext=tick_text,
            tickfont_size=9,
            showgrid=True,
            gridcolor=_GRAY_WARM,
            zeroline=False,
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont_size=9,
        ),
    )
    return fig


def _render_crop_window(scenario: CropScenario) -> None:
    _section("Ventana del cultivo")

    sow_s = _month_label(scenario.sowing_window_start_month, scenario.sowing_window_start_day)
    sow_e = _month_label(scenario.sowing_window_end_month,   scenario.sowing_window_end_day)
    camp  = _month_label(scenario.campaign_start_month,      scenario.campaign_start_day)
    crit  = scenario.critical_stage_summary

    st.caption(
        f"Siembra: {sow_s} – {sow_e}  ·  Campaña modelada desde {camp}  ·  "
        f"Ciclo: {scenario.cycle_length_days} días  ·  Etapas críticas: {crit}"
    )

    fig = _build_timeline_chart(scenario)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})


# ─── Section: Water balance by stage ─────────────────────────────────────────

def _render_water_windows(
    stage_summary: pd.DataFrame,
    scenario: CropScenario,
) -> None:
    _section("Agua en etapas clave")

    if stage_summary.empty:
        st.info("Sin datos de etapas disponibles.")
        return

    # Climatology per stage (mean + percentiles + deficit frequency across all campaigns)
    stage_clim = (
        stage_summary
        .groupby(["stage_key", "stage_label", "is_critical_stage"], as_index=False)
        .agg(
            prec_mean    =("precipitation_stage_mm",  "mean"),
            etc_mean     =("etc_stage_mm",             "mean"),
            bal_mean     =("water_balance_stage_mm",   "mean"),
            bal_p25      =("water_balance_stage_mm",   lambda x: x.quantile(0.25)),
            bal_p75      =("water_balance_stage_mm",   lambda x: x.quantile(0.75)),
            deficit_years=("water_balance_stage_mm",   lambda x: int((x < 0).sum())),
            total_years  =("water_balance_stage_mm",   "count"),
        )
    )

    # Re-order by scenario stage definition
    stage_order = {s.key: i for i, s in enumerate(scenario.stages)}
    stage_clim["_ord"] = stage_clim["stage_key"].map(stage_order)
    stage_clim = stage_clim.sort_values("_ord").drop(columns="_ord")

    # ── Simulacro de napa (selector primero para que el chart lo pueda usar) ───
    # Napa contribution estimates for Departamento Maracó (La Pampa):
    # Based on typical phreatic aquifer depths in La Pampa central (CONICET/INTA):
    #   50th pct scenario: napa ~2.0-2.5m → capillary rise ~0.8-1.2 mm/day → +50mm/ciclo
    #  100th pct scenario: napa ~1.2-1.5m → capillary rise ~2.0-3.0 mm/day → +120mm/ciclo
    # Contribution allocated proportionally to stage duration.
    cycle_days = sum(s.end_day - s.start_day + 1 for s in scenario.stages)
    napa_scenarios = {
        "Sin napa (modelo base)": 0,
        "Napa normal — 50° pct Maracó (~50 mm/ciclo)": 50,
        "Napa favorable — húmedo (~120 mm/ciclo)": 120,
    }
    napa_key = st.selectbox(
        "Simulacro de aporte de napa freática",
        list(napa_scenarios.keys()),
        key=f"napa_{scenario.key}",
        help=(
            "Estimación del aporte capilar de la napa freática al balance hídrico del ciclo. "
            "Basado en profundidades típicas del acuífero freático en Departamento Maracó (La Pampa central). "
            "50° percentil: napa a ~2.0–2.5 m, aporte capilar ~0.8–1.2 mm/día. "
            "Húmedo/favorable: napa a ~1.2–1.5 m, aporte ~2.0–3.0 mm/día. "
            "El aporte se distribuye proporcionalmente por duración de cada etapa."
        ),
    )
    napa_total_mm = napa_scenarios[napa_key]

    # Napa contribution per stage (for bar chart and stage cards)
    napa_per_stage: dict[str, int] = {}
    for _, row in stage_clim.iterrows():
        stage_obj = next((s for s in scenario.stages if s.key == row["stage_key"]), None)
        stage_days = (stage_obj.end_day - stage_obj.start_day + 1) if stage_obj else 0
        napa_per_stage[str(row["stage_key"])] = (
            round(napa_total_mm * stage_days / cycle_days) if cycle_days > 0 else 0
        )

    # ── Bar chart: Prec + napa (apilados) vs ETc by stage ────────────────────
    fig = go.Figure()

    napa_vals = [napa_per_stage.get(str(k), 0) for k in stage_clim["stage_key"]]
    prec_vals = stage_clim["prec_mean"].round(0).tolist()

    # Lluvia: segmento base del bloque "agua disponible" (offsetgroup="agua")
    fig.add_trace(go.Bar(
        name="Lluvia media",
        x=stage_clim["stage_label"],
        y=prec_vals,
        offsetgroup="agua",
        marker_color=_BLUE_LIGHT,
        marker_line_color=_BLUE,
        marker_line_width=1,
        hovertemplate="Lluvia: %{y:.0f} mm<extra></extra>",
    ))
    # Napa: apilada encima de lluvia (base=prec, mismo offsetgroup)
    if napa_total_mm > 0:
        fig.add_trace(go.Bar(
            name=f"Napa (+{napa_total_mm} mm/ciclo)",
            x=stage_clim["stage_label"],
            y=napa_vals,
            base=prec_vals,
            offsetgroup="agua",
            marker_color=_FAV_COLOR,
            marker_line_color="#2D5F35",
            marker_line_width=1,
            hovertemplate="Napa: +%{y:.0f} mm<extra></extra>",
        ))
    # ETc: grupo separado al lado (offsetgroup="etc")
    fig.add_trace(go.Bar(
        name="Demanda (ETc)",
        x=stage_clim["stage_label"],
        y=stage_clim["etc_mean"].round(0),
        offsetgroup="etc",
        marker_color=_ORANGE,
        marker_line_color=_INT_COLOR,
        marker_line_width=1.5,
        hovertemplate="ETc: %{y:.0f} mm<extra></extra>",
    ))

    fig.update_layout(
        **_PLOTLY_BASE,
        height=260,
        barmode="group",
        legend=dict(orientation="h", y=-0.25, xanchor="center", x=0.5, font_size=10,
                    itemclick=False, itemdoubleclick=False),
        xaxis=dict(tickfont_size=9),
        yaxis=dict(title="mm", tickfont_size=9),
        dragmode=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})

    # ── Mini stage cards: balance + P25–P75 + napa ───────────────────────────
    caption_suffix = "" if napa_total_mm == 0 else f" · con aporte napa +{napa_total_mm} mm"
    st.caption(f"Balance hídrico por etapa — media histórica (P25 / P75){caption_suffix}")

    cols = st.columns(len(stage_clim))
    for col, (_, row) in zip(cols, stage_clim.iterrows()):
        is_crit     = bool(row["is_critical_stage"])
        napa_stage  = napa_per_stage.get(str(row["stage_key"]), 0)
        bal         = float(row["bal_mean"]) + napa_stage
        p25         = float(row["bal_p25"]) + napa_stage
        p75         = float(row["bal_p75"]) + napa_stage
        def_years   = int(row["deficit_years"])
        total_years = int(row["total_years"])
        label       = str(row["stage_label"])
        sign        = "+" if bal >= 0 else ""
        val_color   = _REST_COLOR if bal < -30 else (_FAV_COLOR if bal >= 0 else _INT_COLOR)
        tag         = '<div class="ms-stage-card-tag" style="color:#8B4E0C">CRÍTICA</div>' if is_crit else ""
        napa_label  = f'<div class="ms-stage-card-range" style="color:#3A7D44;margin-top:0.15rem">Napa: +{napa_stage} mm</div>' if napa_stage > 0 else ""
        freq_label  = f"{def_years}/{total_years} años con déficit (sin napa)"

        with col:
            st.markdown(
                f"""
                <div class="ms-stage-card {'ms-stage-critical' if is_crit else 'ms-stage-normal'}">
                  <div class="ms-stage-card-label">{label}</div>
                  <div class="ms-stage-card-value" style="color:{val_color}">{sign}{bal:.0f} mm</div>
                  <div class="ms-stage-card-range">P25: {p25:.0f} / P75: {p75:.0f}</div>
                  {napa_label}
                  <div class="ms-stage-card-range" style="margin-top:0.15rem">{freq_label}</div>
                  {tag}
                </div>
                """,
                unsafe_allow_html=True,
            )


# ─── Section: Thermal risk ────────────────────────────────────────────────────

def _render_thermal_risk(
    campaign_summary: pd.DataFrame,
    scenario: CropScenario,
) -> None:
    _section("Temperatura durante el ciclo")

    if campaign_summary.empty:
        return

    temp_mean = float(campaign_summary["mean_temp_cycle_c"].mean())
    temp_min  = float(campaign_summary["mean_temp_cycle_c"].min())
    temp_max  = float(campaign_summary["mean_temp_cycle_c"].max())

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Temp. media del ciclo", f"{temp_mean:.1f} °C")
    with c2:
        st.metric("Campaña más fría", f"{temp_min:.1f} °C")
    with c3:
        st.metric("Campaña más cálida", f"{temp_max:.1f} °C")

    opt_min = scenario.thermal_optimal_min_c
    opt_max = scenario.thermal_optimal_max_c
    tol_min = scenario.thermal_tolerant_min_c
    tol_max = scenario.thermal_tolerant_max_c

    # Scatter: temp per campaign, colored by class
    fig = go.Figure()

    for class_name, color in _CLASS_COLORS.items():
        subset = campaign_summary[campaign_summary["campaign_class"] == class_name]
        if not subset.empty:
            fig.add_trace(go.Scatter(
                x=subset["campaign_label"],
                y=subset["mean_temp_cycle_c"],
                mode="markers",
                name=class_name,
                marker=dict(color=color, size=8, line=dict(color=_WHITE, width=1)),
                hovertemplate="%{x}: %{y:.1f} °C<extra></extra>",
            ))

    fig.add_hrect(
        y0=opt_min, y1=opt_max,
        fillcolor=_FAV_COLOR, opacity=0.10, line_width=0,
    )
    fig.add_hrect(
        y0=tol_min, y1=tol_max,
        fillcolor=_ORANGE, opacity=0.05, line_width=0,
    )
    fig.add_annotation(
        x=0, xref="paper", y=opt_max, text="Óptimo",
        showarrow=False, font=dict(size=8, color=_FAV_COLOR), xanchor="left",
    )
    fig.add_annotation(
        x=0, xref="paper", y=tol_max, text="Tolerable",
        showarrow=False, font=dict(size=8, color=_ORANGE), xanchor="left",
    )

    fig.update_layout(
        **_PLOTLY_BASE,
        height=240,
        xaxis=dict(tickangle=-45, tickfont_size=8),
        yaxis=dict(title="°C", tickfont_size=9),
        legend=dict(orientation="h", y=-0.3, xanchor="center", x=0.5, font_size=9),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})

    st.caption(
        f"Rango óptimo: {opt_min}–{opt_max} °C  ·  "
        f"Rango tolerable: {tol_min}–{tol_max} °C"
    )

    # Cold penalty note
    if (
        scenario.cold_penalty_threshold_c is not None
        and "cold_days" in campaign_summary.columns
    ):
        mean_cold = float(campaign_summary["cold_days"].mean())
        if mean_cold > 0:
            _insight(
                f"Promedio de <b>{mean_cold:.1f} días</b> por campaña con temperatura mínima "
                f"bajo {scenario.cold_penalty_threshold_c:.0f} °C durante el ciclo modelado."
            )

    # Species-specific thermal notes
    species = scenario.species_key
    out_of_opt = campaign_summary[
        (campaign_summary["mean_temp_cycle_c"] < opt_min) |
        (campaign_summary["mean_temp_cycle_c"] > opt_max)
    ]
    pct_out = len(out_of_opt) / len(campaign_summary) * 100 if len(campaign_summary) > 0 else 0

    if species == "wheat":
        _insight(
            "Para trigo, la temperatura durante encañazón y espigazón es crítica. "
            "Heladas tardías (Tmin &lt; 0 °C entre agosto y octubre) pueden destruir "
            "espigas en formación. El rango óptimo aquí refleja el ciclo completo, "
            "no solo las etapas reproductivas."
        )
    elif species == "maize":
        if pct_out > 20:
            _insight(
                f"En <b>{pct_out:.0f}%</b> de las campañas la temperatura media del ciclo "
                f"se alejó del rango óptimo ({opt_min}–{opt_max} °C). "
                "Para maíz, el impacto más severo ocurre cuando Tmax supera 32 °C "
                "durante la emisión de polen (floración)."
            )
        else:
            _insight(
                "La temperatura media del ciclo se mantiene dentro del rango tolerable "
                "en la mayoría de las campañas. El riesgo térmico no es el limitante "
                "principal bajo este escenario."
            )
    elif species == "soy":
        _insight(
            "Para soja, el estrés térmico más relevante ocurre cuando Tmax supera "
            "35 °C durante R1–R3 (floración y cuaje de vainas). "
            "La temperatura media del ciclo es un indicador orientativo: "
            "revisar los picos diarios en las campañas más cálidas."
        )


# ─── Section: Historical stability ───────────────────────────────────────────

def _render_historical_stability(campaign_summary: pd.DataFrame) -> None:
    _section("Estabilidad histórica de campañas")

    if campaign_summary.empty:
        return

    fig = go.Figure()

    _CLASS_BORDERS = {
        "Favorable":  "#2D5F35",
        "Intermedia": _INT_COLOR,
        "Restrictiva": "#8B2020",
    }
    for class_name, color in _CLASS_COLORS.items():
        subset = campaign_summary[campaign_summary["campaign_class"] == class_name]
        if not subset.empty:
            fig.add_trace(go.Bar(
                x=subset["campaign_label"],
                y=subset["agro_score"],
                name=class_name,
                marker_color=color,
                marker_line_color=_CLASS_BORDERS[class_name],
                marker_line_width=1,
                text=subset["agro_score"].round(0).astype(int),
                textposition="outside",
                textfont=dict(size=8, color=_NAVY),
                hovertemplate="%{x}: %{y:.0f} pts<extra></extra>",
            ))

    fig.add_hline(
        y=SCORE_THRESHOLDS["intermediate"],
        line_dash="dot", line_color=_GRAY_WARM, line_width=1.5,
    )
    fig.add_hline(
        y=SCORE_THRESHOLDS["favorable"],
        line_dash="dot", line_color=_FAV_COLOR, line_width=1.5,
    )
    fig.add_annotation(
        x=1, xref="paper", y=SCORE_THRESHOLDS["favorable"] + 2,
        text="Favorable", showarrow=False,
        font=dict(size=8, color=_FAV_COLOR), xanchor="right",
    )
    fig.add_annotation(
        x=1, xref="paper", y=SCORE_THRESHOLDS["intermediate"] + 2,
        text="Intermedio", showarrow=False,
        font=dict(size=8, color=_BLUE), xanchor="right",
    )

    fig.update_layout(
        **{**_PLOTLY_BASE, "margin": dict(l=8, r=8, t=10, b=60)},
        height=300,
        barmode="overlay",
        xaxis=dict(tickangle=-45, tickfont_size=8),
        yaxis=dict(range=[0, 108], title="Score", tickfont_size=9),
        legend=dict(orientation="h", y=-0.35, xanchor="center", x=0.5, font_size=9),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})

    # Class distribution badges
    total = len(campaign_summary)
    fav   = int((campaign_summary["campaign_class"] == "Favorable").sum())
    intr  = int((campaign_summary["campaign_class"] == "Intermedia").sum())
    rest  = int((campaign_summary["campaign_class"] == "Restrictiva").sum())

    st.markdown(
        f"""
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:0.4rem">
          <span class="ms-badge ms-badge-favorable">{fav} Favorables ({fav / total * 100:.0f}%)</span>
          <span class="ms-badge ms-badge-intermedia">{intr} Intermedias ({intr / total * 100:.0f}%)</span>
          <span class="ms-badge ms-badge-restrictiva">{rest} Restrictivas ({rest / total * 100:.0f}%)</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Best / worst call-out
    best  = campaign_summary.loc[campaign_summary["agro_score"].idxmax()]
    worst = campaign_summary.loc[campaign_summary["agro_score"].idxmin()]
    st.caption(
        f"Mejor campaña: {best['campaign_label']} ({best['agro_score']:.0f} pts)  ·  "
        f"Peor campaña: {worst['campaign_label']} ({worst['agro_score']:.0f} pts)"
    )

    # Worst campaign stage-by-stage breakdown
    _render_worst_campaign_breakdown(campaign_summary, worst)


def _render_worst_campaign_breakdown(
    campaign_summary: pd.DataFrame,
    worst_row: pd.Series,
) -> None:
    """Render a compact breakdown of the worst campaign's key indicators."""
    with st.expander(
        f"Detalle de la peor campaña: {worst_row['campaign_label']} "
        f"({worst_row['agro_score']:.0f} pts — {worst_row['campaign_class']})",
        expanded=False,
    ):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Score", f"{worst_row['agro_score']:.0f}")
        with c2:
            prec = worst_row.get("precipitation_cycle_mm")
            st.metric("Lluvia del ciclo", f"{prec:.0f} mm" if prec is not None else "—")
        with c3:
            crit_bal = worst_row.get("critical_balance_mm")
            sign = "+" if (crit_bal or 0) >= 0 else ""
            st.metric("Balance etapas críticas", f"{sign}{crit_bal:.0f} mm" if crit_bal is not None else "—")
        with c4:
            temp = worst_row.get("mean_temp_cycle_c")
            st.metric("Temp. media ciclo", f"{temp:.1f} °C" if temp is not None else "—")

        driver = worst_row.get("score_driver", "")
        if driver:
            st.markdown(
                f'<div class="ms-insight" style="border-left-color:{_REST_COLOR}">'
                f'{driver}</div>',
                unsafe_allow_html=True,
            )
        reading = worst_row.get("interpretation", "")
        if reading:
            st.caption(reading)


# ─── Section: Agronomic reading ───────────────────────────────────────────────

def _render_agronomic_reading(
    global_summary: dict[str, Any],
    soil_summary: dict[str, Any] | None,
    terrain_summary: dict[str, Any] | None,
    scenario: CropScenario,
) -> None:
    _section("Lectura agronómica")

    bullets = generate_scenario_agronomic_reading(
        scenario=scenario,
        global_summary=global_summary,
        soil_summary=soil_summary,
        terrain_summary=terrain_summary,
    )
    for bullet in bullets:
        _insight(bullet)

    # Methodology note (collapsed)
    with st.expander("Supuestos del modelo", expanded=False):
        for note in scenario.methodology_notes:
            st.caption(f"• {note}")
        for assumption in scenario.assumptions:
            st.caption(f"• {assumption}")


# ─── Section: Soja segunda — transition context ───────────────────────────────

def _render_sequence_context(
    climate_bundle: dict[str, Any],
    scenario: CropScenario,
) -> None:
    """Render the trigo→soja-segunda transition window analysis."""
    _section("Contexto de secuencia — transición trigo / soja de segunda")

    monthly_clim = climate_bundle.get("monthly_climatology", pd.DataFrame())
    monthly_by_year = climate_bundle.get("monthly_by_year", pd.DataFrame())

    if monthly_clim.empty:
        st.info("Sin climatología mensual disponible.")
        return

    # November and December are the transition months
    transition_months = monthly_clim[monthly_clim["month"].isin([10, 11, 12])].copy()
    if transition_months.empty:
        st.info("Sin datos para los meses de transición.")
        return

    transition_months = transition_months.sort_values("month")

    _insight(
        "La soja de segunda se siembra después del trigo. En el esquema de la región pampeana, "
        "la cosecha de trigo ocurre típicamente entre <b>finales de octubre y mediados de noviembre</b>. "
        "El período octubre–diciembre concentra las labores de preparación, siembra e implantación."
    )

    # ── Monthly climate strip for Oct–Dec ────────────────────────────────────
    month_labels = {10: "Oct", 11: "Nov", 12: "Dic"}
    st.caption("Condiciones climáticas medias en la ventana de transición (Oct–Dic)")

    cols = st.columns(3)
    for col, (_, row) in zip(cols, transition_months.iterrows()):
        m       = int(row["month"])
        prec    = float(row["precipitation_mm"])
        t_mean  = float(row["temp_mean_c"])
        t_min   = float(row["temp_min_c"])
        label   = month_labels.get(m, str(m))
        with col:
            st.markdown(
                f"""
                <div class="ms-stage-card ms-stage-normal" style="text-align:center">
                  <div class="ms-stage-card-label">{label}</div>
                  <div style="font-size:1rem;font-weight:700;color:{_NAVY}">{prec:.0f} mm</div>
                  <div class="ms-stage-card-range">Tmean {t_mean:.1f} °C</div>
                  <div class="ms-stage-card-range">Tmin {t_min:.1f} °C</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ── Interannual variability in Nov ────────────────────────────────────────
    if not monthly_by_year.empty:
        nov_data = monthly_by_year[monthly_by_year["month"] == 11]["precipitation_mm"]
        dec_data = monthly_by_year[monthly_by_year["month"] == 12]["precipitation_mm"]

        if not nov_data.empty and not dec_data.empty:
            nov_p25 = nov_data.quantile(0.25)
            nov_p75 = nov_data.quantile(0.75)
            dec_p25 = dec_data.quantile(0.25)
            dec_p75 = dec_data.quantile(0.75)
            dry_nov_pct = (nov_data < 40).mean() * 100
            dry_dec_pct = (dec_data < 40).mean() * 100

            _insight(
                f"Variabilidad en la transición: "
                f"noviembre tiene lluvia P25–P75 de <b>{nov_p25:.0f}–{nov_p75:.0f} mm</b>, "
                f"y diciembre de <b>{dec_p25:.0f}–{dec_p75:.0f} mm</b>. "
                f"En <b>{dry_nov_pct:.0f}%</b> de los años, noviembre tuvo menos de 40 mm "
                f"(riesgo de implantación en seco para soja tardía). "
                f"Diciembre: <b>{dry_dec_pct:.0f}%</b> de años con menos de 40 mm."
            )

    # Cycle compression note
    cycle_days = scenario.cycle_length_days
    sow_s = _month_label(scenario.sowing_window_start_month, scenario.sowing_window_start_day)
    sow_e = _month_label(scenario.sowing_window_end_month,   scenario.sowing_window_end_day)
    _insight(
        f"El ciclo de soja de segunda es más corto ({cycle_days} días vs. ~150 de primera). "
        f"Ventana de siembra: {sow_s}–{sow_e}. "
        "Siembras tardías por cosecha de trigo demorada comprimen el ciclo disponible "
        "y corren floración y llenado hacia febrero–marzo, cuando el riesgo de déficit "
        "hídrico y calor tiende a ser mayor."
    )


# ─── Public entry point ───────────────────────────────────────────────────────

def render_scenario_tab(
    scenario: CropScenario,
    analysis_result: AgroAnalysisResult | None,
    soil_summary: dict[str, Any] | None,
    terrain_summary: dict[str, Any] | None,
    climate_bundle: dict[str, Any] | None = None,
) -> None:
    """Render a full agronomic scenario dashboard inside the current Streamlit tab."""
    if analysis_result is None:
        st.error(
            f"No se pudo calcular el análisis para {scenario.label}. "
            "Verificá que el rango de años seleccionado cubre al menos una campaña completa."
        )
        return

    global_summary       = analysis_result["global_summary"]
    campaign_summary     = analysis_result["campaign_summary"]
    stage_summary        = analysis_result["stage_summary"]
    mean_crit_deficit_mm = float(global_summary.get("mean_critical_balance_mm", 0))

    _render_verdict_header(global_summary, scenario)
    st.divider()

    # Soja de segunda: show sequence context before the crop window
    if scenario.key == "soy_second" and climate_bundle is not None:
        _render_sequence_context(climate_bundle, scenario)
        st.divider()

    _render_crop_window(scenario)
    st.divider()

    _render_water_windows(stage_summary, scenario)

    # AWC section injected directly after water windows
    render_soil_water_section(soil_summary, mean_crit_deficit_mm)
    st.divider()

    # Year range filter for historical charts
    available_years = sorted(campaign_summary["campaign_start_year"].tolist()) if "campaign_start_year" in campaign_summary.columns else []
    if len(available_years) > 4:
        min_yr, max_yr = available_years[0], available_years[-1]
        yr_range = st.slider(
            "Filtrar campañas", min_yr, max_yr, (min_yr, max_yr),
            key=f"yr_{scenario.key}", label_visibility="collapsed"
        )
        campaign_summary_filtered = campaign_summary[
            (campaign_summary["campaign_start_year"] >= yr_range[0]) &
            (campaign_summary["campaign_start_year"] <= yr_range[1])
        ]
    else:
        campaign_summary_filtered = campaign_summary

    _render_thermal_risk(campaign_summary_filtered, scenario)
    st.divider()

    _render_historical_stability(campaign_summary_filtered)
    st.divider()

    _render_agronomic_reading(global_summary, soil_summary, terrain_summary, scenario)


# ─── Comparative tab ──────────────────────────────────────────────────────────

def render_comparative_tab(
    analyses: dict[str, AgroAnalysisResult | None],
) -> None:
    """Render a cross-scenario comparative dashboard."""
    from src.agro_scores import (
        build_scenario_comparison_table,
        build_scenario_comparison_insights,
        build_scenario_score_comparison_chart,
        build_aligned_campaign_comparison_table,
        build_aligned_campaign_comparison_insights,
        build_aligned_campaign_gap_chart,
    )
    from src.crops import list_active_crop_scenarios

    valid_analyses = [a for a in analyses.values() if a is not None]
    if not valid_analyses:
        st.warning("No hay análisis disponibles para comparar.")
        return

    _section("Comparativa entre escenarios")
    _insight(
        "Esta vista compara los 5 escenarios productivos bajo las mismas condiciones climáticas "
        "históricas del punto operativo de la finca. No reemplaza el análisis individual por escenario."
    )

    # ── Score comparison table ──────────────────────────────────────────────
    comparison_df = build_scenario_comparison_table(valid_analyses)
    if not comparison_df.empty:
        st.markdown('<span class="ms-section-header">Score medio por escenario</span>', unsafe_allow_html=True)

        fig = go.Figure()
        for _, row in comparison_df.iterrows():
            band = str(row.get("Banda global", ""))
            color = _FAV_COLOR if band == "Favorable" else (_REST_COLOR if band == "Restrictivo" else _INT_COLOR)
            fig.add_trace(go.Bar(
                x=[row["Escenario"]],
                y=[row["Score medio"]],
                name=str(row["Escenario"]),
                marker_color=color,
                text=[f"{row['Score medio']:.0f}"],
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate=(
                    f"<b>{row['Escenario']}</b><br>"
                    f"Score: {row['Score medio']:.1f}<br>"
                    f"Favorables: {row['% favorables']:.0f}%<br>"
                    f"Restrictivas: {row['% restrictivas']:.0f}%"
                    "<extra></extra>"
                ),
            ))

        fig.add_hline(y=SCORE_THRESHOLDS["intermediate"], line_dash="dot", line_color=_GRAY_WARM)
        fig.add_hline(y=SCORE_THRESHOLDS["favorable"],    line_dash="dot", line_color=_FAV_COLOR)
        fig.update_layout(
            **_PLOTLY_BASE,
            height=300,
            showlegend=False,
            yaxis=dict(range=[0, 105], title="Score medio", tickfont_size=9),
            xaxis=dict(tickfont_size=9),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})

        # Compact table
        display_cols = [
            "Escenario", "Score medio", "% favorables", "% restrictivas",
            "Balance medio ciclo (mm)", "Balance medio critico (mm)",
        ]
        available_cols = [c for c in display_cols if c in comparison_df.columns]
        st.dataframe(
            comparison_df[available_cols].style.format({
                "Score medio": "{:.1f}",
                "% favorables": "{:.0f}%",
                "% restrictivas": "{:.0f}%",
                "Balance medio ciclo (mm)": "{:.0f}",
                "Balance medio critico (mm)": "{:.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Insights
        insights = build_scenario_comparison_insights(comparison_df)
        if insights:
            st.markdown('<span class="ms-section-header">Lectura comparativa</span>', unsafe_allow_html=True)
            for insight in insights:
                _insight(insight)

    # ── Aligned campaign comparison (maize early vs late) ───────────────────
    maize_analyses = [a for a in valid_analyses if a["scenario"].species_key == "maize"]
    if len(maize_analyses) == 2:
        st.divider()
        _section("Maíz temprano vs. maíz tardío — campaña por campaña")
        aligned_df = build_aligned_campaign_comparison_table(maize_analyses)
        if not aligned_df.empty:
            gap_fig = build_aligned_campaign_gap_chart(aligned_df)
            gap_fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_family="Montserrat, sans-serif",
                font_color=_NAVY,
                height=260,
            )
            st.plotly_chart(gap_fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})
            aligned_insights = build_aligned_campaign_comparison_insights(aligned_df)
            for insight in aligned_insights:
                _insight(insight)

    # ── Soy first vs second ──────────────────────────────────────────────────
    soy_analyses = [a for a in valid_analyses if a["scenario"].species_key == "soy"]
    if len(soy_analyses) == 2:
        st.divider()
        _section("Soja de primera vs. soja de segunda — campaña por campaña")
        aligned_df = build_aligned_campaign_comparison_table(soy_analyses)
        if not aligned_df.empty:
            gap_fig = build_aligned_campaign_gap_chart(aligned_df)
            gap_fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_family="Montserrat, sans-serif",
                font_color=_NAVY,
                height=260,
            )
            st.plotly_chart(gap_fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})
            aligned_insights = build_aligned_campaign_comparison_insights(aligned_df)
            for insight in aligned_insights:
                _insight(insight)
