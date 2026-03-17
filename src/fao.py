from __future__ import annotations

import pandas as pd

from src.crops import CropScenario, CropStage
from src.eto import (
    calculate_hargreaves_eto,
    compute_reference_eto_daily,
    extraterrestrial_radiation,
)

MIN_CAMPAIGN_COMPLETENESS_PCT = 0.95


def _validate_daily_climate_schema(climate_daily: pd.DataFrame) -> None:
    """Validate minimum required columns for FAO daily calculations."""
    required_columns = {
        "date",
        "temp_mean_c",
        "temp_min_c",
        "temp_max_c",
        "precipitation_mm",
    }
    missing_columns = required_columns.difference(climate_daily.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Faltan columnas climaticas requeridas para FAO: {missing}.")
    if climate_daily.empty:
        raise ValueError("No hay datos climaticos diarios para calcular el modulo FAO.")


def _validate_climate_schema(climate_daily: pd.DataFrame) -> None:
    """Alias kept private to avoid mixing external module responsibilities."""
    _validate_daily_climate_schema(climate_daily)


def _interpolate_stage_kc(stage: CropStage, day_after_sowing: int) -> float:
    """Interpolate Kc linearly within a crop stage."""
    span = max(stage.end_day - stage.start_day, 1)
    progress = min(max((day_after_sowing - stage.start_day) / span, 0.0), 1.0)
    return round(stage.kc_start + (stage.kc_end - stage.kc_start) * progress, 3)


def _resolve_stage(scenario: CropScenario, day_after_sowing: int) -> CropStage:
    """Return the scenario stage matching the day after sowing."""
    for stage in scenario.stages:
        if stage.start_day <= day_after_sowing <= stage.end_day:
            return stage
    return scenario.stages[-1]


def build_campaign_window(
    crop: CropScenario,
    campaign_start_year: int,
) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    """Build the campaign start, end and label, supporting campaigns that cross years."""
    campaign_start = pd.Timestamp(
        year=campaign_start_year,
        month=crop.campaign_start_month,
        day=crop.campaign_start_day,
    )
    campaign_end = campaign_start + pd.Timedelta(days=crop.cycle_length_days - 1)
    campaign_label = f"{campaign_start.year}/{str(campaign_end.year)[-2:]}"
    return campaign_start, campaign_end, campaign_label


def get_available_campaign_years(
    climate_daily: pd.DataFrame,
    crop: CropScenario,
) -> list[int]:
    """Return campaign start years with enough daily data to model the crop cycle."""
    _validate_climate_schema(climate_daily)

    start_date = climate_daily["date"].min()
    end_date = climate_daily["date"].max()
    first_year = int(start_date.year)
    last_year = int(end_date.year)
    available_years: list[int] = []

    for campaign_start_year in range(first_year, last_year + 1):
        campaign_start, campaign_end, _ = build_campaign_window(crop, campaign_start_year)
        if campaign_start >= start_date and campaign_end <= end_date:
            available_years.append(campaign_start_year)

    return available_years


def build_crop_cycle_daily_dataset(
    climate_daily: pd.DataFrame,
    latitude_deg: float,
    crop: CropScenario,
    start_campaign_year: int,
    end_campaign_year: int,
    eto_method: str = "auto",
) -> pd.DataFrame:
    """Build daily campaign records with ETo, Kc and ETc for a crop scenario."""
    eto_daily = compute_reference_eto_daily(
        climate_daily,
        latitude_deg=latitude_deg,
        preferred_method=eto_method,
    )
    campaign_frames: list[pd.DataFrame] = []

    for campaign_start_year in range(start_campaign_year, end_campaign_year + 1):
        campaign_start, campaign_end, campaign_label = build_campaign_window(
            crop,
            campaign_start_year,
        )
        campaign_df = eto_daily.loc[
            (eto_daily["date"] >= campaign_start) & (eto_daily["date"] <= campaign_end)
        ].copy()

        if len(campaign_df) != crop.cycle_length_days:
            continue

        valid_days = int(campaign_df["eto_valid"].sum())
        completeness_pct = valid_days / crop.cycle_length_days
        if completeness_pct < MIN_CAMPAIGN_COMPLETENESS_PCT:
            continue

        campaign_df = campaign_df.loc[campaign_df["eto_valid"]].copy()
        campaign_df["days_after_sowing"] = (
            campaign_df["date"] - campaign_start
        ).dt.days + 1
        campaign_df["campaign_start_year"] = campaign_start_year
        campaign_df["campaign_label"] = campaign_label
        campaign_df["campaign_start_date"] = campaign_start
        campaign_df["campaign_end_date"] = campaign_end
        campaign_df["species_key"] = crop.species_key
        campaign_df["scenario_key"] = crop.key
        campaign_df["scenario_label"] = crop.label
        campaign_df["crop_key"] = crop.key
        campaign_df["crop_label"] = crop.label
        campaign_df["campaign_completeness_pct"] = round(completeness_pct * 100, 1)

        stages = [
            _resolve_stage(crop, int(day_after_sowing))
            for day_after_sowing in campaign_df["days_after_sowing"]
        ]
        campaign_df["stage_key"] = [stage.key for stage in stages]
        campaign_df["stage_label"] = [stage.label for stage in stages]
        campaign_df["is_critical_stage"] = [stage.critical for stage in stages]
        campaign_df["stage_score_weight"] = [stage.score_weight for stage in stages]
        campaign_df["kc"] = [
            _interpolate_stage_kc(stage, int(day_after_sowing))
            for stage, day_after_sowing in zip(stages, campaign_df["days_after_sowing"])
        ]
        campaign_df["etc_mm_day"] = (
            campaign_df["eto_mm_day"].astype(float) * campaign_df["kc"]
        ).round(3)
        campaign_frames.append(campaign_df)

    if not campaign_frames:
        return pd.DataFrame()

    return pd.concat(campaign_frames, ignore_index=True)
