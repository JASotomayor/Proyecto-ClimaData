from __future__ import annotations

from typing import TypedDict

import pandas as pd
import plotly.express as px

from src.crops import CropScenario
from src.fao import build_crop_cycle_daily_dataset

SCORE_COMPONENT_WEIGHTS = {
    "cycle": 28.0,
    "critical": 42.0,
    "thermal": 10.0,
    "reliability": 6.0,
}
SCORE_PENALTIES = {
    "critical_deficit_multiplier": 18.0,
    "cold_day_multiplier": 1.5,
}
SCORE_THRESHOLDS = {
    "favorable": 68.0,
    "intermediate": 45.0,
}


class AgroGlobalSummary(TypedDict):
    """High-level summary of crop agroclimatic performance."""

    crop_label: str
    scenario_label: str
    campaign_count: int
    mean_score: float
    favorable_pct: float
    intermediate_pct: float
    restrictive_pct: float
    mean_balance_mm: float
    mean_critical_balance_mm: float
    best_campaign: str
    worst_campaign: str
    score_band: str
    dominant_driver: str
    executive_message: str
    technical_message: str
    validation_note: str
    interpretation: str


class AgroAnalysisResult(TypedDict):
    """Full result bundle used by the agroclimatic UI."""

    crop: CropScenario
    scenario: CropScenario
    campaign_daily: pd.DataFrame
    campaign_summary: pd.DataFrame
    stage_summary: pd.DataFrame
    global_summary: AgroGlobalSummary
    eto_method: str
    eto_method_label: str
    eto_method_note: str
    methodology_notes: list[str]


def build_aligned_campaign_comparison_table(
    analyses: list[AgroAnalysisResult],
) -> pd.DataFrame:
    """Align campaign summaries across scenarios for campaign-by-campaign comparison."""
    if len(analyses) < 2:
        return pd.DataFrame()

    aligned_df: pd.DataFrame | None = None
    scenario_labels: list[str] = []
    for analysis in analyses:
        scenario_label = analysis["global_summary"]["scenario_label"]
        scenario_labels.append(str(scenario_label))
        summary = analysis["campaign_summary"][
            [
                "campaign_label",
                "agro_score",
                "critical_balance_mm",
                "campaign_class",
            ]
        ].copy()
        summary = summary.rename(
            columns={
                "agro_score": f"score_{scenario_label}",
                "critical_balance_mm": f"critical_balance_{scenario_label}",
                "campaign_class": f"class_{scenario_label}",
            }
        )
        if aligned_df is None:
            aligned_df = summary
        else:
            aligned_df = aligned_df.merge(summary, on="campaign_label", how="inner")

    if aligned_df is None or aligned_df.empty:
        return pd.DataFrame()

    if len(scenario_labels) == 2:
        left_label, right_label = scenario_labels
        aligned_df["score_gap"] = (
            aligned_df[f"score_{left_label}"] - aligned_df[f"score_{right_label}"]
        ).round(1)
        aligned_df["critical_balance_gap"] = (
            aligned_df[f"critical_balance_{left_label}"]
            - aligned_df[f"critical_balance_{right_label}"]
        ).round(1)
        aligned_df["better_scenario"] = aligned_df["score_gap"].apply(
            lambda value: left_label if value > 0 else (right_label if value < 0 else "Empate")
        )
    return aligned_df.sort_values("campaign_label")


def build_aligned_campaign_comparison_insights(
    aligned_df: pd.DataFrame,
) -> list[str]:
    """Build concise insights from an aligned scenario-by-campaign comparison."""
    if aligned_df.empty or "better_scenario" not in aligned_df.columns:
        return []

    comparison_rows = aligned_df.loc[aligned_df["better_scenario"] != "Empate"]
    if comparison_rows.empty:
        return [
            "Los escenarios comparados muestran empates sistematicos en el score historico alineado, por lo que conviene revisar los supuestos antes de sacar conclusiones."
        ]

    wins = comparison_rows["better_scenario"].value_counts()
    leading_scenario = str(wins.index[0])
    leading_count = int(wins.iloc[0])
    total_compared = int(len(comparison_rows))
    mean_gap = float(
        comparison_rows.loc[
            comparison_rows["better_scenario"] == leading_scenario,
            "score_gap",
        ]
        .abs()
        .mean()
    )

    insights = [
        (
            f"En la comparacion campaña por campaña, **{leading_scenario}** supera al escenario alternativo "
            f"en {leading_count} de {total_compared} campañas comparables."
        )
    ]
    if mean_gap >= 8:
        insights.append(
            f"Cuando {leading_scenario} queda por delante, la brecha media de score ronda {mean_gap:.1f} puntos, lo que sugiere una ventaja historica no trivial."
        )
    else:
        insights.append(
            f"Cuando {leading_scenario} queda por delante, la brecha media de score ronda {mean_gap:.1f} puntos, por lo que la ventaja historica debe leerse con moderacion."
        )

    mean_critical_gap = float(
        comparison_rows.loc[
            comparison_rows["better_scenario"] == leading_scenario,
            "critical_balance_gap",
        ]
        .mean()
    )
    if abs(mean_critical_gap) > 30:
        insights.append(
            "La diferencia entre escenarios vuelve a aparecer sobre todo en etapas criticas, no solo en el balance general del ciclo."
        )
    return insights


def build_scenario_comparison_insights(
    comparison_df: pd.DataFrame,
) -> list[str]:
    """Build concise, prudent insights comparing active scenarios of one species."""
    if comparison_df.empty or len(comparison_df) < 2:
        return []

    ordered = comparison_df.sort_values("Score medio", ascending=False).reset_index(drop=True)
    best = ordered.iloc[0]
    second = ordered.iloc[1]
    score_gap = float(best["Score medio"] - second["Score medio"])
    critical_gap = float(best["Balance medio critico (mm)"] - second["Balance medio critico (mm)"])
    restrictive_gap = float(second["% restrictivas"] - best["% restrictivas"])

    insights = [
        (
            f"El escenario que aparece relativamente mejor en este punto es **{best['Escenario']}**, "
            f"con un score medio de {best['Score medio']:.1f} frente a {second['Score medio']:.1f}."
        )
    ]

    if score_gap >= 8:
        insights.append(
            "La diferencia entre escenarios no parece marginal: la brecha de score sugiere un comportamiento historico distinto bajo el mismo punto y periodo."
        )
    else:
        insights.append(
            "La diferencia entre escenarios es acotada y conviene leerla con cautela, porque pequeños cambios de fecha real o de ambiente podrian modificar el orden relativo."
        )

    if critical_gap > 40:
        insights.append(
            f"La principal ventaja comparativa de **{best['Escenario']}** aparece en etapas criticas, con un balance medio aproximadamente {critical_gap:.0f} mm mejor."
        )
    else:
        insights.append(
            "La diferencia entre escenarios no se apoya en una sola variable extrema, sino en un ajuste hidrico general algo mas favorable."
        )

    if restrictive_gap > 10:
        insights.append(
            f"Tambien reduce la proporcion de campanas restrictivas en alrededor de {restrictive_gap:.0f} puntos porcentuales."
        )

    insights.append(
        "Esta comparacion es exploratoria y no reemplaza la validacion con fecha real de siembra, almacenaje de agua del suelo, napa, manejo y objetivo productivo."
    )
    return insights


def build_scenario_comparison_table(
    analyses: list[AgroAnalysisResult],
) -> pd.DataFrame:
    """Build a compact scenario comparison table for the UI."""
    rows: list[dict[str, str | float]] = []
    for analysis in analyses:
        global_summary = analysis["global_summary"]
        rows.append(
            {
                "Escenario": str(global_summary["scenario_label"]),
                "Score medio": float(global_summary["mean_score"]),
                "% favorables": float(global_summary["favorable_pct"]),
                "% restrictivas": float(global_summary["restrictive_pct"]),
                "Balance medio ciclo (mm)": float(global_summary["mean_balance_mm"]),
                "Balance medio critico (mm)": float(global_summary["mean_critical_balance_mm"]),
                "Mejor campana": str(global_summary["best_campaign"]),
                "Banda global": str(global_summary["score_band"]),
            }
        )
    return pd.DataFrame(rows)


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Safely compute a ratio, returning zero when the denominator is not usable."""
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _temperature_component(mean_cycle_temp_c: float, crop: CropScenario) -> float:
    """Approximate thermal suitability contribution for the active scenario."""
    if crop.thermal_optimal_min_c <= mean_cycle_temp_c <= crop.thermal_optimal_max_c:
        return SCORE_COMPONENT_WEIGHTS["thermal"]
    if crop.thermal_tolerant_min_c <= mean_cycle_temp_c <= crop.thermal_tolerant_max_c:
        return 7.0
    return 4.0


def _classify_campaign(score: float) -> str:
    """Map agroclimatic score to a campaign class."""
    if score >= SCORE_THRESHOLDS["favorable"]:
        return "Favorable"
    if score >= SCORE_THRESHOLDS["intermediate"]:
        return "Intermedia"
    return "Restrictiva"


def _derive_campaign_driver(row: pd.Series, crop: CropScenario) -> str:
    """Explain the main factor pulling the campaign score."""
    if row["critical_deficit_share"] >= 0.45:
        return f"Déficit hídrico severo en {crop.critical_stage_summary} (P/ETc < 0.55 en etapas críticas)."
    if row["critical_precip_to_etc_ratio"] < 0.75:
        return f"Oferta hídrica insuficiente en {crop.critical_stage_summary} (relación P/ETc crítica < 0.75)."
    if row["precip_to_etc_ratio"] < 0.8:
        return "Balance P–ETc del ciclo completo negativo: la demanda atmosférica superó la precipitación disponible."
    if (
        row["mean_temp_cycle_c"] < crop.thermal_tolerant_min_c
        or row["mean_temp_cycle_c"] > crop.thermal_tolerant_max_c
    ):
        return "Temperatura media del ciclo fuera del rango tolerable para el escenario evaluado."
    return "Balance hídrico y térmico dentro de rangos aceptables para este esquema."


def _build_campaign_reading(row: pd.Series, crop: CropScenario) -> str:
    """Return a short, user-facing reading of the campaign score."""
    if row["campaign_class"] == "Favorable":
        return "Campaña con ajuste agroclimático favorable: balance hídrico y térmico dentro de rangos productivos."
    if row["campaign_class"] == "Intermedia":
        return f"Campaña intermedia: agua disponible marginal en {crop.critical_stage_summary}; el resultado depende del manejo y del almacenaje del suelo."
    return (
        f"Campaña restrictiva: déficit hídrico en {crop.critical_stage_summary} "
        "con alta probabilidad de impacto sobre rendimiento."
    )


def _derive_global_driver(campaign_summary: pd.DataFrame, crop: CropScenario) -> str:
    """Explain the main structural driver behind the global score."""
    mean_critical_ratio = float(campaign_summary["critical_precip_to_etc_ratio"].mean())
    mean_cycle_ratio = float(campaign_summary["precip_to_etc_ratio"].mean())
    mean_temp = float(campaign_summary["mean_temp_cycle_c"].mean())

    if mean_critical_ratio < 0.75:
        return (
            f"Limitante estructural: balance P–ETc negativo en {crop.critical_stage_summary} "
            f"(relación P/ETc media = {mean_critical_ratio:.2f}). "
            "La oferta hídrica es sistemáticamente inferior a la demanda del cultivo en las etapas de mayor sensibilidad."
        )
    if mean_cycle_ratio < 0.85:
        return (
            f"Balance hídrico del ciclo deficitario en promedio (P/ETc ciclo = {mean_cycle_ratio:.2f}): "
            "la precipitación cubre menos del 85% de la ETc modelada sin considerar almacenaje del suelo."
        )
    if mean_temp < crop.thermal_tolerant_min_c or mean_temp > crop.thermal_tolerant_max_c:
        return "Temperatura media del ciclo fuera del rango tolerable en promedio histórico para el escenario evaluado."
    return "Sin limitante dominante único en la serie histórica bajo este esquema de balance P–ETc simplificado."


def _build_global_messages(
    scenario_label: str,
    mean_score: float,
    favorable_pct: float,
    intermediate_pct: float,
    restrictive_pct: float,
    mean_balance_mm: float,
    mean_critical_balance_mm: float,
    dominant_driver: str,
) -> tuple[str, str, str]:
    """Build user-facing score interpretation without overstating certainty."""
    if mean_score >= SCORE_THRESHOLDS["favorable"]:
        executive_message = (
            f"El punto muestra ajuste agroclimático favorable para {scenario_label.lower()} "
            f"(score medio {mean_score:.1f}/100): la precipitación histórica cubre la demanda "
            "ETc en la mayoría de las campañas, incluyendo las etapas críticas."
        )
    elif mean_score >= SCORE_THRESHOLDS["intermediate"]:
        executive_message = (
            f"Ajuste agroclimático intermedio para {scenario_label.lower()} "
            f"(score medio {mean_score:.1f}/100): hay campañas viables pero el resultado "
            "es sensible al comportamiento hídrico en las etapas de mayor demanda."
        )
    else:
        executive_message = (
            f"Ajuste agroclimático restrictivo para {scenario_label.lower()} "
            f"(score medio {mean_score:.1f}/100): la oferta hídrica histórica no alcanza "
            "a cubrir la ETc en las etapas críticas en la mayoría de las campañas."
        )

    non_restrictive_pct = favorable_pct + intermediate_pct
    technical_message = (
        f"{non_restrictive_pct:.0f}% de campañas en franja intermedia/favorable · "
        f"{restrictive_pct:.0f}% restrictivas · "
        f"balance ciclo completo {mean_balance_mm:+.0f} mm · "
        f"balance etapas críticas {mean_critical_balance_mm:+.0f} mm (P − ETc·Kc) · "
        f"{dominant_driver}"
    )
    validation_note = (
        "Este score expresa ajuste P–ETc bajo calendario fenológico fijo y no incorpora "
        "almacenaje útil del suelo, napa freática, riego ni variación de fecha de siembra. "
        "Contrastar con agua útil al inicio del ciclo y datos de rendimiento históricos del lote."
    )
    return executive_message, technical_message, validation_note


def summarize_crop_stages(campaign_daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily data into stage-level summaries for each campaign."""
    if campaign_daily.empty:
        return pd.DataFrame()

    stage_summary = (
        campaign_daily.groupby(
            [
                "campaign_start_year",
                "campaign_label",
                "stage_key",
                "stage_label",
                "is_critical_stage",
            ],
            as_index=False,
        )
        .agg(
            precipitation_stage_mm=("precipitation_mm", "sum"),
            eto_stage_mm=("eto_mm_day", "sum"),
            etc_stage_mm=("etc_mm_day", "sum"),
            mean_temp_stage_c=("temp_mean_c", "mean"),
            completeness_pct=("campaign_completeness_pct", "first"),
            stage_weight=("stage_score_weight", "mean"),
        )
        .sort_values(["campaign_start_year", "stage_key"])
    )
    stage_summary["water_balance_stage_mm"] = (
        stage_summary["precipitation_stage_mm"] - stage_summary["etc_stage_mm"]
    ).round(1)
    stage_summary["precip_to_etc_stage_ratio"] = stage_summary.apply(
        lambda row: round(
            _safe_ratio(
                float(row["precipitation_stage_mm"]),
                float(row["etc_stage_mm"]),
            ),
            2,
        ),
        axis=1,
    )
    stage_summary["stage_deficit_flag"] = stage_summary["water_balance_stage_mm"] < 0
    return stage_summary


def summarize_crop_campaigns(
    campaign_daily: pd.DataFrame,
    crop: CropScenario,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate daily campaign results into campaign-level indicators."""
    if campaign_daily.empty:
        return pd.DataFrame(), pd.DataFrame()

    stage_summary = summarize_crop_stages(campaign_daily)
    cycle_summary = (
        campaign_daily.groupby(["campaign_start_year", "campaign_label"], as_index=False)
        .agg(
            precipitation_cycle_mm=("precipitation_mm", "sum"),
            eto_cycle_mm=("eto_mm_day", "sum"),
            etc_cycle_mm=("etc_mm_day", "sum"),
            mean_temp_cycle_c=("temp_mean_c", "mean"),
            cold_days_lt5=("temp_min_c", lambda values: int((values < 5).sum())),
            completeness_pct=("campaign_completeness_pct", "first"),
        )
        .sort_values("campaign_start_year")
    )

    critical_summary = (
        stage_summary.loc[stage_summary["is_critical_stage"]]
        .groupby(["campaign_start_year", "campaign_label"], as_index=False)
        .agg(
            precipitation_critical_mm=("precipitation_stage_mm", "sum"),
            eto_critical_mm=("eto_stage_mm", "sum"),
            etc_critical_mm=("etc_stage_mm", "sum"),
            critical_negative_stage_count=("stage_deficit_flag", "sum"),
            worst_critical_balance_mm=("water_balance_stage_mm", "min"),
        )
    )

    campaign_summary = cycle_summary.merge(
        critical_summary,
        on=["campaign_start_year", "campaign_label"],
        how="left",
    )
    numeric_fill_columns = [
        "precipitation_critical_mm",
        "eto_critical_mm",
        "etc_critical_mm",
        "critical_negative_stage_count",
        "worst_critical_balance_mm",
    ]
    campaign_summary[numeric_fill_columns] = campaign_summary[numeric_fill_columns].fillna(0.0)
    campaign_summary["critical_negative_stage_count"] = campaign_summary[
        "critical_negative_stage_count"
    ].astype(int)

    campaign_summary["water_balance_mm"] = (
        campaign_summary["precipitation_cycle_mm"] - campaign_summary["etc_cycle_mm"]
    ).round(1)
    campaign_summary["critical_balance_mm"] = (
        campaign_summary["precipitation_critical_mm"] - campaign_summary["etc_critical_mm"]
    ).round(1)
    campaign_summary["precip_to_etc_ratio"] = campaign_summary.apply(
        lambda row: round(
            _safe_ratio(float(row["precipitation_cycle_mm"]), float(row["etc_cycle_mm"])),
            2,
        ),
        axis=1,
    )
    campaign_summary["critical_precip_to_etc_ratio"] = campaign_summary.apply(
        lambda row: round(
            _safe_ratio(
                float(row["precipitation_critical_mm"]),
                float(row["etc_critical_mm"]),
            ),
            2,
        ),
        axis=1,
    )
    campaign_summary["critical_deficit_share"] = campaign_summary.apply(
        lambda row: round(
            max(
                0.0,
                _safe_ratio(
                    -float(row["critical_balance_mm"]),
                    float(row["etc_critical_mm"]),
                ),
            ),
            2,
        ),
        axis=1,
    )

    weights = crop.score_component_weights or SCORE_COMPONENT_WEIGHTS
    cycle_component = (
        campaign_summary["precip_to_etc_ratio"].clip(lower=0, upper=1.05)
        / 1.05
        * weights["cycle"]
    )
    critical_component = (
        campaign_summary["critical_precip_to_etc_ratio"].clip(lower=0, upper=1.00)
        / 1.00
        * weights["critical"]
    )
    thermal_component = campaign_summary["mean_temp_cycle_c"].apply(
        lambda value: _temperature_component(float(value), crop)
    )
    reliability_component = (
        campaign_summary["completeness_pct"].clip(lower=85, upper=100) - 85
    ) / 15 * weights["reliability"]
    if crop.cold_penalty_threshold_c is None:
        cold_penalty = pd.Series(0.0, index=campaign_summary.index)
    else:
        cold_days = campaign_daily.groupby(
            ["campaign_start_year", "campaign_label"],
            as_index=False,
        ).agg(
            cold_days=("temp_min_c", lambda values: int((values < crop.cold_penalty_threshold_c).sum()))
        )
        campaign_summary = campaign_summary.merge(
            cold_days,
            on=["campaign_start_year", "campaign_label"],
            how="left",
        )
        campaign_summary["cold_days"] = campaign_summary["cold_days"].fillna(0).astype(int)
        cold_penalty = (
            campaign_summary["cold_days"].clip(upper=crop.cold_penalty_cap_days)
            * SCORE_PENALTIES["cold_day_multiplier"]
        )
    critical_deficit_penalty = (
        campaign_summary["critical_deficit_share"]
        * SCORE_PENALTIES["critical_deficit_multiplier"]
    )
    severe_stage_penalty = campaign_summary["worst_critical_balance_mm"].apply(
        lambda value: 5.0 if value < -120 else (2.0 if value < -60 else 0.0)
    )

    campaign_summary["score_cycle_component"] = cycle_component.round(1)
    campaign_summary["score_critical_component"] = critical_component.round(1)
    campaign_summary["score_thermal_component"] = thermal_component.round(1)
    campaign_summary["score_reliability_component"] = reliability_component.round(1)
    campaign_summary["score_penalty_total"] = (
        cold_penalty + critical_deficit_penalty + severe_stage_penalty
    ).round(1)
    campaign_summary["agro_score"] = (
        cycle_component
        + critical_component
        + thermal_component
        + reliability_component
        - cold_penalty
        - critical_deficit_penalty
        - severe_stage_penalty
    ).clip(lower=0, upper=100).round(1)
    campaign_summary["campaign_class"] = campaign_summary["agro_score"].apply(
        _classify_campaign
    )
    campaign_summary["score_driver"] = campaign_summary.apply(
        lambda row: _derive_campaign_driver(row, crop),
        axis=1,
    )
    campaign_summary["interpretation"] = campaign_summary.apply(
        lambda row: _build_campaign_reading(row, crop),
        axis=1,
    )
    campaign_summary["scenario_label"] = crop.label
    campaign_summary["crop_label"] = crop.label
    return campaign_summary, stage_summary


def build_global_summary(
    campaign_summary: pd.DataFrame,
    crop: CropScenario,
) -> AgroGlobalSummary:
    """Build a concise global interpretation across campaigns."""
    if campaign_summary.empty:
        raise ValueError("No hay campanas disponibles para resumir.")

    best_campaign = campaign_summary.loc[campaign_summary["agro_score"].idxmax()]
    worst_campaign = campaign_summary.loc[campaign_summary["agro_score"].idxmin()]
    favorable_pct = (campaign_summary["campaign_class"] == "Favorable").mean() * 100
    intermediate_pct = (campaign_summary["campaign_class"] == "Intermedia").mean() * 100
    restrictive_pct = (campaign_summary["campaign_class"] == "Restrictiva").mean() * 100
    mean_score = float(campaign_summary["agro_score"].mean())
    mean_balance_mm = float(campaign_summary["water_balance_mm"].mean())
    mean_critical_balance_mm = float(campaign_summary["critical_balance_mm"].mean())

    if mean_score >= SCORE_THRESHOLDS["favorable"]:
        score_band = "Favorable"
        interpretation = (
            f"El punto muestra un ajuste agroclimatico relativamente favorable para {crop.label.lower()} "
            "en una proporcion importante de las campanas analizadas."
        )
    elif mean_score >= SCORE_THRESHOLDS["intermediate"]:
        score_band = "Intermedio"
        interpretation = (
            "El ajuste agroclimatico historico aparece intermedio: el resultado del sistema "
            "depende fuertemente de como se comporten las etapas criticas."
        )
    else:
        score_band = "Restrictivo"
        interpretation = (
            f"El ajuste agroclimatico historico aparece restrictivo para {crop.label.lower()}, "
            f"especialmente cuando la oferta de agua no acompana {crop.critical_stage_summary}."
        )

    dominant_driver = _derive_global_driver(campaign_summary, crop)
    executive_message, technical_message, validation_note = _build_global_messages(
        scenario_label=crop.label,
        mean_score=mean_score,
        favorable_pct=favorable_pct,
        intermediate_pct=intermediate_pct,
        restrictive_pct=restrictive_pct,
        mean_balance_mm=mean_balance_mm,
        mean_critical_balance_mm=mean_critical_balance_mm,
        dominant_driver=dominant_driver,
    )

    return {
        "crop_label": crop.label,
        "scenario_label": crop.label,
        "campaign_count": int(len(campaign_summary)),
        "mean_score": round(mean_score, 1),
        "favorable_pct": round(float(favorable_pct), 1),
        "intermediate_pct": round(float(intermediate_pct), 1),
        "restrictive_pct": round(float(restrictive_pct), 1),
        "mean_balance_mm": round(mean_balance_mm, 1),
        "mean_critical_balance_mm": round(mean_critical_balance_mm, 1),
        "best_campaign": str(best_campaign["campaign_label"]),
        "worst_campaign": str(worst_campaign["campaign_label"]),
        "score_band": score_band,
        "dominant_driver": dominant_driver,
        "executive_message": executive_message,
        "technical_message": technical_message,
        "validation_note": validation_note,
        "interpretation": interpretation,
    }


def run_crop_agro_analysis(
    climate_daily: pd.DataFrame,
    latitude_deg: float,
    crop: CropScenario,
    start_campaign_year: int,
    end_campaign_year: int,
) -> AgroAnalysisResult:
    """Run a simplified agroclimatic suitability analysis for a crop scenario."""
    campaign_daily = build_crop_cycle_daily_dataset(
        climate_daily=climate_daily,
        latitude_deg=latitude_deg,
        crop=crop,
        start_campaign_year=start_campaign_year,
        end_campaign_year=end_campaign_year,
    )
    if campaign_daily.empty:
        raise ValueError(
            "No hay campanas completas disponibles para este escenario dentro del rango seleccionado."
        )

    eto_method = str(campaign_daily["eto_method"].mode().iat[0])
    eto_method_label = str(campaign_daily["eto_method_label"].mode().iat[0])
    eto_method_note = str(campaign_daily["eto_method_note"].mode().iat[0])
    campaign_summary, stage_summary = summarize_crop_campaigns(campaign_daily, crop)
    global_summary = build_global_summary(campaign_summary, crop)
    methodology_notes = [
        crop.reference_note,
        "El score expresa ajuste agroclimático relativo (P − ETc·Kc), no predicción de rendimiento.",
        f"ETo calculada por {eto_method_label}. ETc = ETo × Kc (coeficientes de cultivo FAO Paper 56).",
        "La precipitación se usa como oferta bruta sin modelar almacenaje del suelo, napa freática, "
        "infiltración diferencial ni riego; el score subestima el potencial en suelos con alta AWC "
        "o con agua útil al inicio del ciclo.",
        "Las etapas críticas tienen ponderación doble en el score porque concentran la mayor sensibilidad "
        "del cultivo al déficit hídrico y térmico (floración, cuaje, llenado de grano).",
    ]
    return {
        "crop": crop,
        "scenario": crop,
        "campaign_daily": campaign_daily,
        "campaign_summary": campaign_summary,
        "stage_summary": stage_summary,
        "global_summary": global_summary,
        "eto_method": eto_method,
        "eto_method_label": eto_method_label,
        "eto_method_note": eto_method_note,
        "methodology_notes": methodology_notes,
    }


def build_campaign_balance_chart(campaign_summary: pd.DataFrame):
    """Build precipitation vs ETc chart by campaign."""
    chart_df = campaign_summary.melt(
        id_vars=["campaign_label"],
        value_vars=["precipitation_cycle_mm", "etc_cycle_mm"],
        var_name="series",
        value_name="value_mm",
    )
    chart_df["series"] = chart_df["series"].map(
        {
            "precipitation_cycle_mm": "Precipitacion del ciclo",
            "etc_cycle_mm": "ETc del ciclo",
        }
    )
    return px.bar(
        chart_df,
        x="campaign_label",
        y="value_mm",
        color="series",
        barmode="group",
        labels={
            "campaign_label": "Campana",
            "value_mm": "mm",
            "series": "Serie",
        },
    ).update_layout(margin=dict(l=10, r=10, t=30, b=10))


def build_campaign_score_chart(campaign_summary: pd.DataFrame):
    """Build score evolution chart by campaign."""
    fig = px.line(
        campaign_summary,
        x="campaign_label",
        y="agro_score",
        markers=True,
        color="campaign_class",
        labels={
            "campaign_label": "Campana",
            "agro_score": "Score agroclimatico",
            "campaign_class": "Clase",
        },
        title="Evolucion del score agroclimatico",
    ).update_layout(margin=dict(l=10, r=10, t=45, b=10), yaxis_range=[0, 100])
    fig.add_hline(y=SCORE_THRESHOLDS["intermediate"], line_dash="dot", line_color="#8b8b8b")
    fig.add_hline(y=SCORE_THRESHOLDS["favorable"], line_dash="dot", line_color="#4f7d39")
    return fig


def build_campaign_class_distribution_chart(campaign_summary: pd.DataFrame):
    """Build class distribution chart for campaign outcomes."""
    counts = (
        campaign_summary.groupby("campaign_class", as_index=False)
        .size()
        .rename(columns={"size": "campaign_count"})
    )
    return px.bar(
        counts,
        x="campaign_class",
        y="campaign_count",
        color="campaign_class",
        labels={
            "campaign_class": "Clase",
            "campaign_count": "Cantidad de campanas",
        },
        title="Distribucion de categorias",
    ).update_layout(margin=dict(l=10, r=10, t=45, b=10), showlegend=False)


def build_critical_balance_chart(campaign_summary: pd.DataFrame):
    """Build a campaign chart centered on critical-stage water balance."""
    chart_df = campaign_summary.sort_values("critical_balance_mm", ascending=True).copy()
    return px.bar(
        chart_df,
        x="campaign_label",
        y="critical_balance_mm",
        color="campaign_class",
        labels={
            "campaign_label": "Campana",
            "critical_balance_mm": "Balance hidrico en etapas criticas (mm)",
            "campaign_class": "Clase",
        },
        title="Balance en etapas criticas",
    ).update_layout(margin=dict(l=10, r=10, t=45, b=10))


def build_scenario_score_comparison_chart(comparison_df: pd.DataFrame):
    """Build a compact chart comparing average score by active scenario."""
    return px.bar(
        comparison_df,
        x="Escenario",
        y="Score medio",
        color="Banda global",
        labels={
            "Escenario": "Escenario",
            "Score medio": "Score medio",
            "Banda global": "Banda",
        },
        title="Comparacion de score medio por escenario",
    ).update_layout(margin=dict(l=10, r=10, t=45, b=10), yaxis_range=[0, 100])


def build_aligned_campaign_gap_chart(aligned_df: pd.DataFrame):
    """Build a chart showing score gap by campaign between two aligned scenarios."""
    if aligned_df.empty or "score_gap" not in aligned_df.columns:
        return px.bar(title="Sin campañas comparables")

    chart_df = aligned_df.copy()
    chart_df["gap_sign"] = chart_df["score_gap"].apply(
        lambda value: "Primero mejor" if value > 0 else ("Segundo mejor" if value < 0 else "Empate")
    )
    return px.bar(
        chart_df,
        x="campaign_label",
        y="score_gap",
        color="gap_sign",
        labels={
            "campaign_label": "Campaña",
            "score_gap": "Brecha de score",
            "gap_sign": "Lectura",
        },
        title="Brecha de score por campaña",
    ).update_layout(margin=dict(l=10, r=10, t=45, b=10))
