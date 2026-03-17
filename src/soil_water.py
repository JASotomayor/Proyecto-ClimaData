"""Simplified soil water capacity estimation and contextual rendering.

Uses a pedotransfer approach to estimate the Available Water Capacity (AWC)
from soil texture fractions. The estimates are intentionally coarse (±25%)
and suitable only for rapid agroclimatic screening, not field-scale design.

Reference ranges adapted from:
  - Saxton & Rawls (2006) simplified equations
  - FAO Irrigation & Drainage Paper 56 (Annex 2)
  - USDA-NRCS soil water characteristics data
"""
from __future__ import annotations

from typing import Any

import streamlit as st

# ─── Design tokens ─────────────────────────────────────────────────────────────
_NAVY       = "#1E3953"
_BLUE       = "#607E93"
_BLUE_LIGHT = "#8FA8BB"
_ORANGE     = "#EF9645"
_GRAY_LIGHT = "#F7F6F5"
_GRAY_WARM  = "#D8D4D0"
_FAV_COLOR  = "#3A7D44"
_INT_COLOR  = "#EF9645"
_REST_COLOR = "#BF4040"
_FAV_BG     = "#D6EFDC"
_INT_BG     = "#FDE8CC"
_REST_BG    = "#F5D5D5"

# Default root zone depth for extensive dryland crops in Argentina (cm)
_DEFAULT_ROOT_DEPTH_CM = 70


def _awc_rate_mm_per_cm(sand_pct: float | None, clay_pct: float | None) -> tuple[float, float]:
    """Return (awc_low, awc_high) in mm per cm of soil depth.

    Based on simplified texture-class pedotransfer ranges. The midpoint
    is used for interpretation; the range reflects estimation uncertainty.
    """
    if sand_pct is None or clay_pct is None:
        return 1.3, 1.7  # generic loam fallback

    if sand_pct >= 70:
        return 0.8, 1.1   # Arenoso
    if sand_pct >= 55 and clay_pct < 20:
        return 1.0, 1.4   # Franco-arenoso
    if clay_pct >= 45:
        return 1.2, 1.6   # Arcilloso (AWC drops at very high clay)
    if clay_pct >= 30:
        return 1.4, 1.9   # Franco-arcilloso / arcillo-limoso
    if sand_pct < 20 and clay_pct < 25:
        return 1.6, 2.0   # Franco-limoso / limoso
    return 1.4, 1.8       # Franco (default mid-range)


def estimate_root_zone_awc(
    soil_summary: dict[str, Any],
    root_depth_cm: int = _DEFAULT_ROOT_DEPTH_CM,
) -> dict[str, Any]:
    """Estimate root-zone AWC and return an interpretation bundle.

    Returns a dict with:
      - awc_low_mm, awc_high_mm: range of estimated total AWC
      - awc_mid_mm: midpoint (used for comparisons)
      - root_depth_cm: root zone depth used
      - texture_class: resolved texture
      - method_note: limitation statement
    """
    sand = soil_summary.get("sand_pct")
    clay = soil_summary.get("clay_pct")
    texture = soil_summary.get("texture_class", "No disponible")

    rate_low, rate_high = _awc_rate_mm_per_cm(sand, clay)
    awc_low  = round(rate_low  * root_depth_cm, 0)
    awc_high = round(rate_high * root_depth_cm, 0)
    awc_mid  = round((awc_low + awc_high) / 2, 0)

    return {
        "awc_low_mm":    awc_low,
        "awc_high_mm":   awc_high,
        "awc_mid_mm":    awc_mid,
        "root_depth_cm": root_depth_cm,
        "texture_class": texture,
        "method_note": (
            f"Estimación orientativa basada en textura ({texture}) y zona radicular "
            f"asumida de {root_depth_cm} cm. Incertidumbre ±25%. "
            "No incluye variación con profundidad, compactación ni napa."
        ),
    }


def build_awc_vs_deficit_interpretation(
    awc_mid_mm: float,
    mean_critical_deficit_mm: float,
) -> tuple[str, str]:
    """Return (color_hex, interpretation_text) comparing AWC to critical-stage deficit.

    ``mean_critical_deficit_mm`` is negative when demand exceeds supply.
    """
    if mean_critical_deficit_mm >= 0:
        return _FAV_COLOR, (
            "El balance medio en etapas críticas es positivo. "
            "La reserva hídrica del suelo no estaría bajo presión en campañas promedio."
        )

    deficit = abs(mean_critical_deficit_mm)

    if deficit <= awc_mid_mm * 0.4:
        return _FAV_COLOR, (
            f"El déficit medio en etapas críticas ({deficit:.0f} mm) es menor al "
            f"40% de la reserva útil estimada (~{awc_mid_mm:.0f} mm). "
            "El suelo puede compensar este déficit en la mayoría de los años."
        )
    if deficit <= awc_mid_mm * 0.8:
        return _INT_COLOR, (
            f"El déficit medio en etapas críticas ({deficit:.0f} mm) alcanza "
            f"entre el 40% y el 80% de la reserva útil estimada (~{awc_mid_mm:.0f} mm). "
            "El suelo puede amortiguar parcialmente, pero en años secos el déficit "
            "probablemente supere la reserva disponible."
        )
    return _REST_COLOR, (
        f"El déficit medio en etapas críticas ({deficit:.0f} mm) supera el "
        f"80% de la reserva útil estimada (~{awc_mid_mm:.0f} mm). "
        "El buffer del suelo es insuficiente para compensar en años deficitarios: "
        "el riesgo hídrico es estructural para este escenario."
    )


def render_soil_water_section(
    soil_summary: dict[str, Any] | None,
    mean_critical_deficit_mm: float | None,
) -> None:
    """Render the soil water capacity section inside a scenario dashboard."""
    st.markdown(
        '<span class="ms-section-header">Capacidad de almacenaje del suelo</span>',
        unsafe_allow_html=True,
    )

    if not soil_summary or not soil_summary.get("available"):
        st.caption(
            "Sin datos de suelo disponibles. Esta sección requiere información "
            "de textura para estimar la reserva útil."
        )
        return

    awc = estimate_root_zone_awc(soil_summary)
    awc_low  = awc["awc_low_mm"]
    awc_high = awc["awc_high_mm"]
    awc_mid  = awc["awc_mid_mm"]
    root_cm  = awc["root_depth_cm"]
    texture  = awc["texture_class"]

    # ── KPI row ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Reserva útil estimada", f"{awc_low:.0f}–{awc_high:.0f} mm")
    with c2:
        st.metric("Zona radicular asumida", f"{root_cm} cm")
    with c3:
        st.metric("Textura", texture)

    # ── Interpretation vs critical deficit ──────────────────────────────────
    if mean_critical_deficit_mm is not None:
        color, interp = build_awc_vs_deficit_interpretation(awc_mid, mean_critical_deficit_mm)
        st.markdown(
            f'<div class="ms-insight" style="border-left-color:{color}">{interp}</div>',
            unsafe_allow_html=True,
        )

    # ── AWC bar visual ────────────────────────────────────────────────────────
    deficit_val = abs(mean_critical_deficit_mm) if mean_critical_deficit_mm is not None else 0.0
    if deficit_val > 0:
        pct_covered = min(100.0, awc_mid / deficit_val * 100)
        bar_color   = _FAV_COLOR if pct_covered >= 80 else (_INT_COLOR if pct_covered >= 40 else _REST_COLOR)

        st.markdown(
            f"""
            <div style="margin-top:0.6rem">
              <div style="font-size:0.65rem;font-weight:700;color:{_BLUE};
                          text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.3rem">
                Cobertura de la reserva sobre el déficit crítico medio
              </div>
              <div style="background:{_GRAY_WARM};border-radius:999px;height:10px;overflow:hidden">
                <div style="background:{bar_color};width:{pct_covered:.0f}%;
                            height:100%;border-radius:999px;transition:width 0.4s"></div>
              </div>
              <div style="font-size:0.7rem;color:{_NAVY};margin-top:0.25rem;font-weight:600">
                {pct_covered:.0f}% — reserva ~{awc_mid:.0f} mm vs déficit ~{deficit_val:.0f} mm
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption(awc["method_note"])
