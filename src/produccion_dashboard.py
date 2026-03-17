"""Production dashboard tab — MAGyP regional yield data vs agro scores.

Renders the "Producción Regional" tab in the Streamlit app.
Data source: MAGyP/SIIA Estimaciones Agrícolas, Departamento Maracó, La Pampa.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.agro_scores import SCORE_THRESHOLDS

_PROC_DIR = Path("data/trebolares/processed")

# ─── Design tokens (same as scenario_dashboard) ───────────────────────────────
_NAVY       = "#1E3953"
_BLUE       = "#607E93"
_BLUE_LIGHT = "#8FA8BB"
_ORANGE     = "#EF9645"
_GRAY_LIGHT = "#F7F6F5"
_GRAY_WARM  = "#D8D4D0"
_WHITE      = "#FFFFFF"

_FAV_COLOR  = "#3A7D44"
_INT_COLOR  = "#EF9645"
_REST_COLOR = "#BF4040"

_CLASS_COLORS: dict[str, str] = {
    "Favorable":  _FAV_COLOR,
    "Intermedia": _INT_COLOR,
    "Restrictiva": _REST_COLOR,
}

_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_family="Montserrat, sans-serif",
    font_color=_NAVY,
    margin=dict(l=8, r=8, t=28, b=36),
)

# scenario_key → (agro parquet prefix, cultivo label in MAGyP data, production parquet key)
_CROP_MAP = {
    "maize_early": ("maize_early", "Maíz",           "maize"),
    "wheat":       ("wheat",       "Trigo",           "wheat"),
    "soy_first":   ("soy_first",   "Soja de primera", "soy_first"),
    "soy_second":  ("soy_second",  "Soja de segunda", "soy_second"),
}


# ─── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def _load_merged(agro_prefix: str, prod_key: str) -> pd.DataFrame:
    agro_path = _PROC_DIR / f"agro_{agro_prefix}_campaign_summary.parquet"
    prod_path = _PROC_DIR / f"produccion_{prod_key}.parquet"

    if not agro_path.exists() or not prod_path.exists():
        return pd.DataFrame()

    agro = pd.read_parquet(agro_path)
    prod = pd.read_parquet(prod_path)
    merged = agro.merge(prod, left_on="campaign_start_year", right_on="anio", how="inner")
    merged = merged[merged["campaign_start_year"] >= 2001]
    merged = merged.sort_values("campaign_start_year")
    return merged


@st.cache_data
def _load_production_full(prod_key: str, year_min: int = 0, year_max: int = 9999) -> pd.DataFrame:
    path = _PROC_DIR / f"produccion_{prod_key}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path).sort_values("anio")
    return df[(df["anio"] >= year_min) & (df["anio"] <= year_max)]


@st.cache_data
def _load_meta() -> dict:
    import json
    path = _PROC_DIR / "produccion_meta.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─── Chart helpers ─────────────────────────────────────────────────────────────

def _render_yield_history(prod: pd.DataFrame, label: str) -> None:
    """Long historical yield series with 10-year rolling mean."""
    st.markdown("#### Serie histórica de rendimiento")
    valid = prod.dropna(subset=["rendimiento_kgxha"])
    if valid.empty:
        st.info("Sin datos de rendimiento disponibles.")
        return

    rolling = valid.set_index("anio")["rendimiento_kgxha"].rolling(10, min_periods=3).mean()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=valid["anio"], y=valid["rendimiento_kgxha"],
        name="Rendimiento anual",
        marker_color=_BLUE_LIGHT,
    ))
    fig.add_trace(go.Scatter(
        x=rolling.index, y=rolling.values,
        name="Media móvil 10 años",
        line=dict(color=_NAVY, width=2),
        mode="lines",
    ))
    fig.update_layout(
        **_PLOTLY_BASE,
        height=300,
        yaxis_title="kg/ha",
        xaxis_title="Año",
        legend=dict(orientation="h", y=-0.25),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})


def _render_area(prod: pd.DataFrame) -> None:
    """Sown vs harvested area evolution."""
    st.markdown("#### Superficie sembrada vs cosechada")
    cols_needed = {"superficie_sembrada_ha", "superficie_cosechada_ha", "anio"}
    if not cols_needed.issubset(prod.columns):
        st.info("Sin datos de superficie disponibles.")
        return
    valid = prod.dropna(subset=["superficie_sembrada_ha", "superficie_cosechada_ha"])
    if valid.empty:
        st.info("Sin datos de superficie disponibles.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=valid["anio"], y=valid["superficie_sembrada_ha"],
        name="Sembrada", fill="tozeroy",
        line=dict(color=_BLUE_LIGHT, width=1.5),
        fillcolor="rgba(96,126,147,0.18)",
    ))
    fig.add_trace(go.Scatter(
        x=valid["anio"], y=valid["superficie_cosechada_ha"],
        name="Cosechada", fill="tozeroy",
        line=dict(color=_NAVY, width=2),
        fillcolor="rgba(30,57,83,0.22)",
    ))
    fig.update_layout(
        **_PLOTLY_BASE,
        height=280,
        yaxis_title="ha",
        xaxis_title="Año",
        legend=dict(orientation="h", y=-0.28),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})


def _render_deficit_vs_yield(merged: pd.DataFrame) -> None:
    """Panel: impacto del déficit hídrico sobre el rendimiento por nivel de déficit crítico."""

    valid = merged.dropna(subset=["critical_balance_mm", "rendimiento_kgxha"])
    if len(valid) < 5:
        st.info("Pocos datos para el análisis.")
        return

    # Umbrales agronómicos (suelo franco ~120–140 mm AWC):
    #  > −60 mm: el perfil compensa completamente
    #  −60 a −120 mm: compensación parcial posible
    #  < −120 mm: excede la capacidad del suelo
    _D_LABELS  = ["Sin déficit severo", "Déficit moderado", "Déficit severo"]
    _D_COLORS  = [_FAV_COLOR, _INT_COLOR, _REST_COLOR]
    _D_BORDERS = ["#2D5F35", "#C07830", "#8B2020"]
    _D_BG      = ["#D6EFDC", "#FDE8CC", "#F5D5D5"]
    _D_TX      = ["#2E5E37", "#8B4E0C", "#822020"]
    _D_THRESH  = ["&gt; −60 mm", "−60 a −120 mm", "&lt; −120 mm"]

    def _classify(v: float) -> str:
        if v > -60:   return "Sin déficit severo"
        if v > -120:  return "Déficit moderado"
        return "Déficit severo"

    valid = valid.copy()
    valid["deficit_class"] = valid["critical_balance_mm"].apply(_classify)

    # Stats per group
    by_class = {
        lbl: valid[valid["deficit_class"] == lbl]["rendimiento_kgxha"]
        for lbl in _D_LABELS
    }
    means = {lbl: float(s.mean()) if len(s) else None for lbl, s in by_class.items()}
    ns    = {lbl: len(s) for lbl, s in by_class.items()}

    mean_no  = means["Sin déficit severo"]
    mean_sev = means["Déficit severo"]
    yield_gap     = (mean_no - mean_sev) if (mean_no and mean_sev) else None
    yield_gap_pct = (yield_gap / mean_no * 100) if yield_gap and mean_no else None
    n_severe  = ns["Déficit severo"]
    n_total   = len(valid)
    r_critical = round(float(valid["critical_balance_mm"].corr(valid["rendimiento_kgxha"])), 2)
    r_cycle    = round(float(valid["water_balance_mm"].corr(valid["rendimiento_kgxha"])), 2) \
                 if "water_balance_mm" in valid.columns else None

    # ── Título ────────────────────────────────────────────────────────────────
    st.markdown("#### Impacto del déficit hídrico sobre el rendimiento")
    st.caption(
        "Campañas agrupadas por nivel de déficit en etapas críticas (floración y llenado). "
        "Déficit modelado P − ETc, sin almacenaje de suelo · MAGyP Maracó 2001–2024."
    )

    # ── Tarjetas de grupo: una fila por clase, visual y compacta ─────────────
    cards_html = '<div style="display:flex;flex-direction:column;gap:0.5rem;margin-bottom:1rem">'
    for lbl, color, bg, tx, thresh in zip(_D_LABELS, _D_COLORS, _D_BG, _D_TX, _D_THRESH):
        m   = means[lbl]
        n   = ns[lbl]
        pct = n / n_total * 100 if n_total else 0
        val = f"{m:,.0f} kg/ha" if m else "—"
        diff_html = ""
        if lbl == "Déficit severo" and yield_gap:
            diff_html = (
                f'<span style="font-size:0.8rem;color:{color};font-weight:700;margin-left:0.5rem">'
                f'−{yield_gap:.0f} kg/ha vs sin déficit</span>'
            )
        cards_html += (
            f'<div style="background:{bg};border-left:4px solid {color};border-radius:0 8px 8px 0;'
            f'padding:0.65rem 1rem;display:flex;align-items:center;justify-content:space-between;'
            f'flex-wrap:wrap;gap:0.4rem">'
            f'<div>'
            f'<div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.06em;color:{tx}">{lbl}</div>'
            f'<div style="font-size:0.72rem;color:{tx};opacity:0.8">{thresh} · {n} campañas ({pct:.0f}%)</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:1.3rem;font-weight:700;color:{tx}">{val}</div>'
            f'<div style="font-size:0.72rem;color:{tx};opacity:0.8">rendimiento medio</div>'
            f'{diff_html}'
            f'</div>'
            f'</div>'
        )
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    # ── Gráfico único: distribución por clase (box + puntos) ─────────────────
    fig = go.Figure()
    for lbl, color, border in zip(_D_LABELS, _D_COLORS, _D_BORDERS):
        sub = by_class[lbl]
        if sub.empty:
            continue
        # Puntos individuales (años)
        years = valid[valid["deficit_class"] == lbl]["campaign_start_year"].astype(str)
        fig.add_trace(go.Box(
            y=sub,
            name=lbl,
            marker_color=color,
            line_color=border,
            line_width=2,
            fillcolor="rgba({},{},{},0.27)".format(
                int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            ),
            boxmean=True,
            boxpoints="all",
            jitter=0.35,
            pointpos=0,
            marker=dict(size=7, opacity=0.8,
                        line=dict(color=border, width=1)),
            text=years,
            hovertemplate="%{text}: %{y:.0f} kg/ha<extra></extra>",
        ))
        # Anotación de media directamente sobre cada grupo
        if means[lbl]:
            fig.add_annotation(
                x=lbl, y=means[lbl],
                text=f"<b>{means[lbl]:,.0f}</b>",
                showarrow=False,
                font=dict(size=10, color=border, family="Montserrat"),
                xanchor="center", yanchor="bottom",
                yshift=6,
            )

    fig.update_layout(
        **{**_PLOTLY_BASE, "margin": dict(l=8, r=8, t=20, b=20)},
        height=340,
        showlegend=False,
        xaxis=dict(tickfont_size=10),
        yaxis=dict(title="Rendimiento kg/ha", tickfont_size=9, gridcolor=_GRAY_WARM),
        dragmode=False,
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})
    st.caption(
        "Cada punto es una campaña. La línea central es la mediana; la cruz (+) es la media. "
        "El déficit modelado es bruto (P − ETc sin reserva de suelo): "
        "años con déficit moderado pueden no reflejarse en pérdida real si el perfil estaba bien cargado al inicio."
    )

    # ── Conclusión: pill radio selector ───────────────────────────────────────
    gap_str = (
        f"La diferencia observada entre el grupo sin déficit severo y el grupo severo es "
        f"<b>~{yield_gap:.0f} kg/ha ({yield_gap_pct:.0f}%)</b>. "
        if yield_gap else ""
    )
    bullets = [
        (
            f"<b>El déficit crítico concentra el riesgo, pero no es catastrófico.</b> "
            f"De {n_total} campañas analizadas, {n_severe} ({n_severe/n_total*100:.0f}%) tuvieron déficit severo "
            f"en floración y llenado. {gap_str}"
            f"El suelo franco actúa como buffer: déficits moderados (−60 a −120 mm) no siempre se expresan en pérdida."
        ),
        (
            f"<b>Conclusión:</b> el déficit hídrico no es una limitación estructural de la zona. "
            f"Es un factor de riesgo interanual que aparece con intensidad suficiente para afectar rendimiento "
            f"en aproximadamente 1 de cada {round(n_total/max(n_severe,1))} campañas. "
            f"El momento del déficit importa más que el volumen total "
            + (f"(r etapas críticas = {r_critical:.2f} vs r ciclo completo = {r_cycle:.2f})." if r_cycle else f"(r = {r_critical:.2f} en etapas críticas).")
        ),
    ]
    from src.carousel import render_swipe_carousel
    render_swipe_carousel(bullets)


def _render_score_vs_yield(merged: pd.DataFrame) -> None:
    """Scatter: agro score vs observed yield, colored by class."""
    st.markdown("#### Score agroclimático vs rendimiento observado")
    if merged.empty:
        st.info("Sin datos combinados score/rendimiento para este cultivo.")
        return

    valid = merged.dropna(subset=["agro_score", "rendimiento_kgxha"])
    if len(valid) < 4:
        st.info("Pocos años en común para el gráfico de dispersión.")
        return

    r = valid["agro_score"].corr(valid["rendimiento_kgxha"])

    fig = go.Figure()
    for cls, color in _CLASS_COLORS.items():
        sub = valid[valid["campaign_class"] == cls]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["agro_score"], y=sub["rendimiento_kgxha"],
            mode="markers+text",
            name=cls,
            text=sub["campaign_start_year"].astype(str),
            textposition="top center",
            textfont=dict(size=9),
            marker=dict(color=color, size=9, opacity=0.85),
        ))

    # Trend line
    import numpy as np
    m, b = np.polyfit(valid["agro_score"], valid["rendimiento_kgxha"], 1)
    x_range = [valid["agro_score"].min(), valid["agro_score"].max()]
    fig.add_trace(go.Scatter(
        x=x_range, y=[m * xi + b for xi in x_range],
        mode="lines", name=f"Tendencia (r={r:.2f})",
        line=dict(color=_ORANGE, width=2, dash="dash"),
        showlegend=True,
    ))

    fig.update_layout(
        **_PLOTLY_BASE,
        height=380,
        xaxis_title="Score agroclimático",
        yaxis_title="Rendimiento kg/ha",
        legend=dict(orientation="h", y=-0.22),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})


def _render_dual_axis(merged: pd.DataFrame) -> None:
    """Dual-axis: score (bar) + yield (line) by year."""
    st.markdown("#### Evolución comparada: score y rendimiento por campaña")
    if merged.empty or len(merged) < 4:
        st.info("Sin datos suficientes.")
        return

    valid = merged.dropna(subset=["agro_score", "rendimiento_kgxha"])
    bar_colors = [_CLASS_COLORS.get(c, _BLUE) for c in valid["campaign_class"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=valid["campaign_start_year"], y=valid["agro_score"],
        name="Score", marker_color=bar_colors, opacity=0.75,
        yaxis="y1",
    ))
    fig.add_trace(go.Scatter(
        x=valid["campaign_start_year"], y=valid["rendimiento_kgxha"],
        name="Rendimiento (kg/ha)", mode="lines+markers",
        line=dict(color=_NAVY, width=2),
        marker=dict(size=6),
        yaxis="y2",
    ))
    fig.update_layout(
        **{**_PLOTLY_BASE, "margin": dict(l=8, r=50, t=28, b=60)},
        height=320,
        yaxis=dict(title="Score", range=[0, 100]),
        yaxis2=dict(title="kg/ha", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=-0.3),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})


def _render_yield_by_class(merged: pd.DataFrame) -> None:
    """Box plot: yield distribution by agronomic class."""
    st.markdown("#### Rendimiento según clase agroclimática")
    if merged.empty:
        st.info("Sin datos.")
        return

    valid = merged.dropna(subset=["campaign_class", "rendimiento_kgxha"])
    fig = go.Figure()
    for cls in ["Favorable", "Intermedia", "Restrictiva"]:
        sub = valid[valid["campaign_class"] == cls]["rendimiento_kgxha"]
        if sub.empty:
            continue
        fig.add_trace(go.Box(
            y=sub, name=cls,
            marker_color=_CLASS_COLORS[cls],
            boxmean=True,
        ))
    fig.update_layout(
        **_PLOTLY_BASE,
        height=300,
        yaxis_title="kg/ha",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})


def _render_kpi_row(meta: dict, prod_key: str, merged: pd.DataFrame) -> None:
    """Single headline KPI: rendimiento medio regional."""
    crop_meta = meta.get("crops", {}).get(prod_key, {})
    if not crop_meta.get("available"):
        return
    rend = crop_meta.get("rendimiento_mean", 0)
    st.metric(
        "Rendimiento medio regional",
        f"{rend:.0f} kg/ha",
        help="MAGyP/SIIA · Dto. Maracó, La Pampa · 2001–presente",
    )


# ─── Public entry point ────────────────────────────────────────────────────────

def render_produccion_tab() -> None:
    """Render the Producción Regional tab."""
    st.markdown(
        '<p class="ms-section-label">PRODUCCIÓN REGIONAL</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "**Fuente:** MAGyP — Estimaciones Agrícolas por departamento · "
        "Departamento **Maracó, La Pampa**",
        help="Datos oficiales del Ministerio de Agricultura, Ganadería y Pesca de Argentina (SIIA).",
    )

    meta = _load_meta()
    if not meta:
        st.warning("No se encontraron metadatos de producción. Ejecutá scripts/04_fetch_produccion_regional.py primero.")
        return

    crop_options = {
        "Maíz":            ("maize_early", "maize"),
        "Trigo":           ("wheat",       "wheat"),
        "Soja de primera": ("soy_first",   "soy_first"),
        "Soja de segunda": ("soy_second",  "soy_second"),
    }

    selected_label = st.selectbox(
        "Cultivo",
        options=list(crop_options.keys()),
        key="prod_crop_filter",
    )
    selected = [selected_label]

    for crop_label, (agro_prefix, prod_key) in crop_options.items():
        if crop_label not in selected:
            continue
        st.markdown(
            f'<span class="ms-section-header">{crop_label}</span>',
            unsafe_allow_html=True,
        )

        prod_full = _load_production_full(prod_key, year_min=2001)
        merged    = _load_merged(agro_prefix, prod_key)

        _render_kpi_row(meta, prod_key, merged)
        _render_yield_history(prod_full, crop_label)
        _render_deficit_vs_yield(merged)
        _render_dual_axis(merged)
        _render_area(prod_full)

        st.divider()
