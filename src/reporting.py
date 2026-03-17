from __future__ import annotations

from typing import Any

from src.utils import GeoPoint


def _build_climate_bullets(climate_indicators: dict[str, Any] | None) -> list[str]:
    """Build concise climate insights with clear separation of observation and inference."""
    if not climate_indicators:
        return [
            "Serie climática NASA POWER no disponible para este intento."
        ]

    bullets = [
        (
            f"Precipitación media anual {climate_indicators['annual_precip_mean']:.0f} mm · "
            f"temperatura media anual {climate_indicators['annual_temp_mean']:.1f} °C "
            "(NASA POWER ERA5-reanalysis, serie diaria 2001–presente)."
        ),
        (
            f"Año más seco del período: {climate_indicators['driest_year']['year']} "
            f"({climate_indicators['driest_year']['value']:.0f} mm) · "
            f"año más húmedo: {climate_indicators['wettest_year']['year']} "
            f"({climate_indicators['wettest_year']['value']:.0f} mm). "
            f"Amplitud interanual de {climate_indicators['wettest_year']['value'] - climate_indicators['driest_year']['value']:.0f} mm."
        ),
        (
            f"Estabilidad hídrica: {climate_indicators['water_stability'].lower()} · "
            f"riesgo de sequía: {climate_indicators['drought_risk'].lower()} "
            "(basado en CV interanual de precipitación y déficit del año seco respecto a la media)."
        ),
    ]

    frost_months = climate_indicators.get("frost_months", [])
    if frost_months:
        bullets.append(
            "Riesgo de helada por temperatura mínima media mensual: "
            + ", ".join(frost_months)
            + ". Heladas tardías sobre cultivos de verano requieren seguimiento en años con anomalía térmica negativa."
        )
    else:
        bullets.append(
            "Sin meses con temperatura mínima media mensual cercana a 0 °C. "
            "El perfil térmico es compatible con los principales cultivos de verano sin restricción por helada en el promedio histórico."
        )

    return bullets


def _build_soil_bullets(soil_summary: dict[str, Any] | None) -> list[str]:
    """Build soil observations without overstating certainty."""
    if not soil_summary or not soil_summary.get("available"):
        return [
            "Datos de suelo no disponibles (SoilGrids WCS sin respuesta). "
            "Contrastar con cartografía INTA o análisis propio del lote."
        ]

    bullets = [
        (
            f"Textura superficial estimada: {soil_summary['texture_class'].lower()} "
            f"(arena {soil_summary.get('sand_pct', '—')}%, "
            f"limo {soil_summary.get('silt_pct', '—')}%, "
            f"arcilla {soil_summary.get('clay_pct', '—')}%). "
            "SoilGrids 250m v2.0, horizonte 0–5 cm."
        )
    ]

    if soil_summary.get("ph") is not None:
        oc = soil_summary.get("organic_carbon")
        oc_str = f" · carbono orgánico {oc:.1f} g/kg" if oc else ""
        bullets.append(
            f"pH superficial {soil_summary['ph']}{oc_str} · "
            f"CEC {soil_summary.get('cec', '—')} cmolc/kg."
        )

    observations = soil_summary.get("observations", [])
    if observations:
        bullets.append(observations[0])

    return bullets


def _build_terrain_bullets(terrain_summary: dict[str, Any] | None) -> list[str]:
    """Build terrain and drainage bullets with cautious interpretation."""
    if not terrain_summary or not terrain_summary.get("available"):
        return [
            "Datos de relieve no disponibles (OpenTopoData sin respuesta). "
            "Evaluar posición topográfica y riesgo de drenaje en visita de campo."
        ]

    return [
        (
            f"Elevación {terrain_summary['elevation_m']} m s.n.m. · "
            f"relieve local: {terrain_summary['relief_class'].lower()} "
            "(OpenTopoData SRTM 30m)."
        ),
        (
            f"Riesgo de acumulación de agua: {terrain_summary['drainage_risk'].lower()} "
            "según posición topográfica relativa estimada. "
            "Verificar presencia de bajos, huella de anegamiento y escurrimiento en campo."
        ),
    ]


def _build_methodological_bullet(
    soil_summary: dict[str, Any] | None,
    terrain_summary: dict[str, Any] | None,
) -> str:
    """Build the final validation note for field use."""
    if soil_summary and soil_summary.get("available") and terrain_summary and terrain_summary.get("available"):
        return (
            "Validar en visita: bajos y huellas de anegamiento, estructura y compactación del suelo, "
            "profundidad de napa en al menos un pozo de monitoreo, y variabilidad interna del lote."
        )
    return (
        "Usar este diagnóstico como filtro previo para la visita. "
        "Validar en campo: suelo (textura, compactación, profundidad efectiva), "
        "drenaje, napa freática y variación interna del lote."
    )


def generate_executive_summary(
    point: GeoPoint,
    climate_indicators: dict[str, Any] | None,
    soil_summary: dict[str, Any] | None,
    terrain_summary: dict[str, Any] | None,
) -> list[str]:
    """Generate a concise executive summary for non-technical users."""
    bullets: list[str] = [
        f"Punto de análisis: {point.lat:.6f}°, {point.lon:.6f}° · fuente climática: NASA POWER ERA5-reanalysis.",
    ]
    bullets.extend(_build_climate_bullets(climate_indicators))
    bullets.extend(_build_soil_bullets(soil_summary))
    bullets.extend(_build_terrain_bullets(terrain_summary))
    bullets.append(_build_methodological_bullet(soil_summary, terrain_summary))

    deduped_bullets: list[str] = []
    for bullet in bullets:
        if bullet not in deduped_bullets:
            deduped_bullets.append(bullet)

    if len(deduped_bullets) < 5:
        deduped_bullets.append(
            "Este diagnóstico integra datos remotos (NASA POWER, SoilGrids, SRTM) y no reemplaza "
            "la verificación agronómica del lote."
        )

    return deduped_bullets[:8]


def generate_scenario_agronomic_reading(
    scenario: Any,
    global_summary: dict[str, Any],
    soil_summary: dict[str, Any] | None,
    terrain_summary: dict[str, Any] | None,
) -> list[str]:
    """Generate scenario-specific agronomic reading bullets.

    Combines the agroclimatic score result with the farm's soil and terrain
    context to produce actionable bullets tailored to the crop scenario.
    """
    bullets: list[str] = []
    species  = getattr(scenario, "species_key", "")
    crit_stg = getattr(scenario, "critical_stage_summary", "etapas críticas")
    mean_score      = float(global_summary.get("mean_score", 0))
    fav_pct         = float(global_summary.get("favorable_pct", 0))
    rest_pct        = float(global_summary.get("restrictive_pct", 0))
    mean_crit_bal   = float(global_summary.get("mean_critical_balance_mm", 0))
    driver          = global_summary.get("dominant_driver", "")
    best_campaign   = global_summary.get("best_campaign", "")
    worst_campaign  = global_summary.get("worst_campaign", "")

    # ── Score interpretation ──────────────────────────────────────────────
    if mean_score >= 68:
        bullets.append(
            f"Ajuste agroclimático <b>favorable</b> para {scenario.label.lower()} "
            f"(score medio {mean_score:.1f}/100 · {fav_pct:.0f}% de campañas en franja favorable). "
            f"Mejor campaña de la serie: {best_campaign}."
        )
    elif mean_score >= 45:
        bullets.append(
            f"Ajuste agroclimático <b>intermedio</b> para {scenario.label.lower()} "
            f"(score medio {mean_score:.1f}/100 · {fav_pct:.0f}% favorables · {rest_pct:.0f}% restrictivas). "
            f"El balance P–ETc en {crit_stg} es el factor discriminante entre campañas viables y deficitarias."
        )
    else:
        bullets.append(
            f"Ajuste agroclimático <b>restrictivo</b> para {scenario.label.lower()} "
            f"(score medio {mean_score:.1f}/100 · {rest_pct:.0f}% de campañas restrictivas). "
            f"Campaña más limitante de la serie: {worst_campaign}."
        )

    # ── Driver ────────────────────────────────────────────────────────────
    if driver:
        bullets.append(driver)

    # ── Critical stage water balance ──────────────────────────────────────
    if mean_crit_bal < -40:
        bullets.append(
            f"Balance P–ETc en {crit_stg}: <b>{mean_crit_bal:.0f} mm</b> en promedio histórico. "
            "Déficit estructural: la precipitación no cubre la demanda del cultivo en las etapas "
            "de mayor sensibilidad en la mayoría de los años. Sin riego ni aportes del suelo, "
            "el impacto sobre rendimiento es esperable y recurrente."
        )
    elif mean_crit_bal < 0:
        bullets.append(
            f"Balance P–ETc en {crit_stg}: <b>{mean_crit_bal:.0f} mm</b> en promedio histórico. "
            "Déficit moderado: el almacenaje de agua del suelo al inicio del ciclo puede compensar "
            "parcialmente la brecha. La variabilidad interanual es determinante."
        )
    else:
        bullets.append(
            f"Balance P–ETc en {crit_stg}: <b>+{mean_crit_bal:.0f} mm</b> en promedio histórico. "
            "La precipitación cubre la ETc en etapas críticas en promedio, aunque años con "
            "distribución intraestacional desfavorable pueden resultar deficitarios."
        )

    # ── Species-specific risk note ────────────────────────────────────────
    if species == "wheat":
        bullets.append(
            "Trigo: monitorear Tmin durante encañazón–espigazón (DC30–DC60). "
            "Heladas con Tmin ≤ −2 °C en antesis destruyen espiguillas; las de espigazón "
            "tardía afectan también calidad. Exceso de lluvia en madurez compromete calidad "
            "panadera (peso hectolítrico, proteína, caída Hagberg). "
            "El modelo actual no penaliza exceso de lluvia en cosecha — evaluar en campo."
        )
    elif species == "maize":
        bullets.append(
            "Maíz: días con Tmax > 32 °C durante floración (R1) afectan la viabilidad del "
            "polen y la sincronía espiga–estigma. El score P–ETc no captura este riesgo "
            "térmico diario; revisar las campañas con balance hídrico positivo pero "
            "temperatura máxima elevada durante el período de floración."
        )
    elif species == "soy":
        bullets.append(
            "Soja: estrés térmico con Tmax > 35 °C durante R1–R3 provoca aborto de flores "
            "y vainas con independencia del balance hídrico. El período R5–R6 (llenado) "
            "concentra el mayor costo de rendimiento ante déficit combinado hídrico–térmico. "
            "El score actual no discrimina el componente térmico diario en floración."
        )

    # ── Soil texture modulator ────────────────────────────────────────────
    if soil_summary and soil_summary.get("available"):
        texture = soil_summary.get("texture_class", "").lower()
        sand    = soil_summary.get("sand_pct")
        clay    = soil_summary.get("clay_pct")

        if sand is not None and sand > 60:
            bullets.append(
                f"Textura arenosa (arena {sand:.0f}%): AWC estimada baja (~70–90 mm/m). "
                "Los déficits P–ETc modelados subestiman el riesgo real porque el suelo "
                "no acumula reservas suficientes para compensar los períodos secos entre lluvias."
            )
        elif clay is not None and clay > 45:
            bullets.append(
                f"Textura arcillosa (arcilla {clay:.0f}%): AWC estimada alta (>150 mm/m). "
                "El almacenaje puede atenuar los déficits hídricos, pero en años húmedos "
                "el riesgo de anegamiento y de compactación por laboreo en condiciones "
                "inadecuadas puede limitar implantación y desarrollo radicular."
            )
        elif "franca" in texture or "franco" in texture:
            clay_val = soil_summary.get("clay_pct", "—")
            bullets.append(
                f"Textura franca (arcilla ~{clay_val}%): AWC estimada moderada (110–140 mm/m). "
                "El suelo puede compensar parcialmente los déficits P–ETc brutos modelados; "
                "el score tiende a ser conservador en este tipo de perfil."
            )

    # ── Terrain modulator ─────────────────────────────────────────────────
    if terrain_summary and terrain_summary.get("available"):
        drainage = terrain_summary.get("drainage_risk", "").lower()
        if drainage == "alto":
            bullets.append(
                "Posición topográfica baja con riesgo de acumulación hídrica. "
                "En años con exceso pluvial, el anegamiento puede ser tan limitante "
                "como el déficit. El score no penaliza excesos; validar presencia "
                "de bajos y capacidad de escurrimiento en campo."
            )
        elif drainage == "moderado" and species in ("maize", "soy"):
            bullets.append(
                "Posición topográfica intermedia: la heterogeneidad interna del lote "
                "puede generar ambientes con respuestas distintas ante el mismo año "
                "climático. Considerar zonificación por ambientes en el manejo."
            )

    # ── Validation note ───────────────────────────────────────────────────
    bullets.append(global_summary.get("validation_note", ""))

    return [b for b in bullets if b]


def get_online_scope_sections() -> tuple[list[str], list[str]]:
    """Return the methodological scope section content."""
    estimable = [
        "Precipitación histórica diaria, variabilidad interanual y estacionalidad — NASA POWER ERA5-reanalysis (~55 km de resolución espacial).",
        "Temperatura media, mínima y máxima del período analizado (misma fuente).",
        "Riesgo relativo de heladas por mes según temperatura mínima media mensual histórica.",
        "Score de aptitud agroclimática por escenario (maíz temprano/tardío, trigo, soja 1ª/2ª): balance P − ETc·Kc por etapa fenológica, con calendario fijo.",
        "ETo por Hargreaves-Samani (FAO Paper 56) con factor de calibración regional 0.88 (INTA EEA Anguil).",
        "ETc = ETo × Kc; coeficientes de cultivo por etapa basados en FAO Paper 56.",
        "Propiedades de suelo superficiales (0–5 cm): textura, pH, carbono orgánico, CEC — SoilGrids 250m v2.0 (ISRIC, 2020).",
        "Elevación, relieve local e inferencia de riesgo de acumulación hídrica — OpenTopoData SRTM 30m.",
        "Contexto de secuencia trigo–soja de segunda: ventana de implantación y balance hídrico residual.",
        "Comparación de score entre los 5 escenarios bajo el mismo punto y período.",
        "Correlación histórica score–rendimiento con datos MAGyP/SIIA para Departamento Maracó, La Pampa.",
    ]
    not_confirmable = [
        "Profundidad real de napa freática ni su variación estacional o por ambiente.",
        "Capacidad productiva efectiva del lote sin visita agronómica ni historial de manejo.",
        "Compactación, estructura, profundidad efectiva del perfil ni conductividad hidráulica.",
        "Salinidad, sodicidad, pH en profundidad ni heterogeneidades localizadas sin muestreo.",
        "Rendimiento esperado: el score expresa ajuste P–ETc relativo bajo supuestos fijos, no predice rendimiento.",
        "Efecto de genotipo, fecha real de siembra, densidad, sanidad ni decisiones de manejo.",
        "Variabilidad interna del lote a escala sub-campo — NASA POWER tiene ~55 km de resolución; SoilGrids 250 m.",
        "Almacenaje de agua útil al inicio del ciclo ni su variación entre lotes y años.",
    ]
    return estimable, not_confirmable
