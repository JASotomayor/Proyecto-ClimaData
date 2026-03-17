from __future__ import annotations

from typing import Any, TypedDict

import pandas as pd
import requests
from src.config import (
    FROST_RISK_THRESHOLD_C,
    MONTH_LABELS,
    NASA_POWER_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
)

NASA_PARAMETERS = {
    "PRECTOTCORR": "precipitation_mm",
    "T2M": "temp_mean_c",
    "T2M_MIN": "temp_min_c",
    "T2M_MAX": "temp_max_c",
}
CLIMATE_VALUE_COLUMNS = list(NASA_PARAMETERS.values())
MONTH_LABEL_MAP = dict(enumerate(MONTH_LABELS, start=1))


class AnnualExtremum(TypedDict):
    """Annual extreme indicator payload."""

    year: int
    value: float


class AgroclimaticIndicators(TypedDict):
    """Simplified agroclimatic indicators derived from historical aggregates."""

    annual_precip_mean: float
    wettest_year: AnnualExtremum
    driest_year: AnnualExtremum
    annual_temp_mean: float
    frost_months: list[str]
    rainfall_seasonality: str
    rainfall_cv: float
    water_stability: str
    drought_risk: str
    frost_risk: str


class ClimateOutputs(TypedDict):
    """Standard climate tables produced by prepare_climate_outputs."""

    daily: pd.DataFrame
    annual: pd.DataFrame
    monthly_by_year: pd.DataFrame
    monthly_climatology: pd.DataFrame


def _validate_nasa_power_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate the NASA POWER payload and return the parameter block."""
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("NASA POWER no devolvio el bloque 'properties' esperado.")

    parameter_block = properties.get("parameter")
    if not isinstance(parameter_block, dict):
        raise ValueError("NASA POWER no devolvio el bloque 'parameter' esperado.")

    missing_parameters = [
        parameter for parameter in NASA_PARAMETERS if parameter not in parameter_block
    ]
    if missing_parameters:
        missing = ", ".join(missing_parameters)
        raise ValueError(
            f"NASA POWER devolvio un payload incompleto. Faltan variables: {missing}."
        )

    return parameter_block


def _build_nasa_power_dataframe(
    parameter_block: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Build a normalized dataframe from the NASA POWER parameter block."""
    date_keys = list(parameter_block["PRECTOTCORR"].keys())
    if not date_keys:
        raise ValueError("NASA POWER no devolvio fechas para el punto consultado.")

    for parameter in NASA_PARAMETERS:
        values = parameter_block.get(parameter, {})
        if not isinstance(values, dict):
            raise ValueError(
                f"La variable {parameter} llego en un formato no esperado desde NASA POWER."
            )
        if list(values.keys()) != date_keys:
            raise ValueError(
                "NASA POWER devolvio series con fechas inconsistentes entre variables."
            )

    raw_data: dict[str, Any] = {
        "date": pd.to_datetime(date_keys, format="%Y%m%d", errors="coerce"),
    }
    for parameter, column_name in NASA_PARAMETERS.items():
        raw_data[column_name] = pd.to_numeric(
            pd.Series(parameter_block[parameter]).replace(-999, pd.NA),
            errors="coerce",
        )

    df = pd.DataFrame(raw_data)
    df = df.dropna(subset=["date"])
    df = df.dropna(subset=CLIMATE_VALUE_COLUMNS, how="all")
    if df.empty:
        raise ValueError(
            "NASA POWER devolvio datos vacios o solo valores faltantes para ese periodo."
        )

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["month_label"] = df["month"].map(MONTH_LABEL_MAP)
    return df


def _validate_climate_dataframe(climate_df: pd.DataFrame) -> None:
    """Validate the minimum schema needed to compute climate outputs."""
    required_columns = {"date", "year", "month", "month_label", *CLIMATE_VALUE_COLUMNS}
    missing_columns = required_columns.difference(climate_df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Faltan columnas climaticas requeridas: {missing}.")
    if climate_df.empty:
        raise ValueError("No hay datos climaticos para procesar.")


def _ensure_calendar_fields(climate_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure year/month helper columns exist for normalized daily climate series."""
    if "date" not in climate_df.columns:
        raise ValueError("La serie climatica no incluye la columna 'date'.")

    enriched = climate_df.copy()
    enriched["date"] = pd.to_datetime(enriched["date"], errors="coerce")
    enriched = enriched.dropna(subset=["date"])
    if "year" not in enriched.columns:
        enriched["year"] = enriched["date"].dt.year
    if "month" not in enriched.columns:
        enriched["month"] = enriched["date"].dt.month
    if "month_label" not in enriched.columns:
        enriched["month_label"] = enriched["month"].map(MONTH_LABEL_MAP)
    return enriched


def fetch_nasa_power_daily(
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Fetch daily NASA POWER climate variables for a point."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start": f"{start_year}0101",
        "end": f"{end_year}1231",
        "community": "AG",
        "parameters": ",".join(NASA_PARAMETERS),
        "format": "JSON",
    }
    response = requests.get(
        NASA_POWER_BASE_URL,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("NASA POWER devolvio una respuesta JSON invalida.") from exc

    parameter_block = _validate_nasa_power_payload(payload)
    return _build_nasa_power_dataframe(parameter_block)


def prepare_climate_outputs(climate_df: pd.DataFrame) -> ClimateOutputs:
    """Aggregate daily climate data into annual and monthly outputs."""
    climate_df = _ensure_calendar_fields(climate_df)
    _validate_climate_dataframe(climate_df)

    annual = (
        climate_df.groupby("year", as_index=False)
        .agg(
            precipitation_mm=("precipitation_mm", "sum"),
            temp_mean_c=("temp_mean_c", "mean"),
            temp_min_c=("temp_min_c", "mean"),
            temp_max_c=("temp_max_c", "mean"),
        )
        .sort_values("year")
    )
    precipitation_mean = annual["precipitation_mm"].mean()
    if precipitation_mean and not pd.isna(precipitation_mean):
        annual["precipitation_anomaly_pct"] = (
            (annual["precipitation_mm"] - precipitation_mean)
            / precipitation_mean
            * 100
        ).round(1)
    else:
        annual["precipitation_anomaly_pct"] = 0.0

    monthly_by_year = (
        climate_df.groupby(["year", "month", "month_label"], as_index=False)
        .agg(
            precipitation_mm=("precipitation_mm", "sum"),
            temp_mean_c=("temp_mean_c", "mean"),
            temp_min_c=("temp_min_c", "mean"),
            temp_max_c=("temp_max_c", "mean"),
        )
        .sort_values(["year", "month"])
    )

    monthly_climatology = (
        monthly_by_year.groupby(["month", "month_label"], as_index=False)
        .agg(
            precipitation_mm=("precipitation_mm", "mean"),
            temp_mean_c=("temp_mean_c", "mean"),
            temp_min_c=("temp_min_c", "mean"),
            temp_max_c=("temp_max_c", "mean"),
        )
        .sort_values("month")
    )
    monthly_climatology["month_label"] = pd.Categorical(
        monthly_climatology["month_label"],
        categories=MONTH_LABELS,
        ordered=True,
    )

    return {
        "daily": climate_df,
        "annual": annual,
        "monthly_by_year": monthly_by_year,
        "monthly_climatology": monthly_climatology,
    }


def compute_agroclimatic_indicators(
    annual_df: pd.DataFrame,
    monthly_climatology: pd.DataFrame,
) -> AgroclimaticIndicators:
    """Compute simplified agroclimatic indicators from climate aggregates.

    The frost and drought indicators are intentionally coarse approximations.
    They are suitable for rapid screening, not for field-scale agronomic certainty.
    """
    if annual_df.empty or monthly_climatology.empty:
        raise ValueError("No hay suficientes datos climaticos agregados para calcular indicadores.")

    wettest_year = annual_df.loc[annual_df["precipitation_mm"].idxmax()]
    driest_year = annual_df.loc[annual_df["precipitation_mm"].idxmin()]
    annual_precip_mean = float(annual_df["precipitation_mm"].mean())
    annual_temp_mean = float(annual_df["temp_mean_c"].mean())
    rainfall_cv = float(
        annual_df["precipitation_mm"].std(ddof=0) / annual_precip_mean * 100
        if annual_precip_mean
        else 0.0
    )
    frost_months = (
        monthly_climatology.loc[
            monthly_climatology["temp_min_c"] <= FROST_RISK_THRESHOLD_C,
            "month_label",
        ]
        .astype(str)
        .tolist()
    )

    wet_half = monthly_climatology.nlargest(6, "precipitation_mm")[
        "precipitation_mm"
    ].sum()
    dry_half = monthly_climatology.nsmallest(6, "precipitation_mm")[
        "precipitation_mm"
    ].sum()
    seasonality_ratio = wet_half / dry_half if dry_half else float("inf")

    if seasonality_ratio < 1.35:
        rainfall_seasonality = "Distribucion relativamente balanceada"
    elif seasonality_ratio < 1.8:
        rainfall_seasonality = "Estacionalidad moderada"
    else:
        rainfall_seasonality = "Fuerte concentracion estacional"

    if rainfall_cv < 15:
        water_stability = "Alta"
    elif rainfall_cv < 25:
        water_stability = "Media"
    else:
        water_stability = "Baja"

    # Simplified drought flag based on interannual rainfall dispersion and the driest-year gap.
    driest_ratio = (
        float(driest_year["precipitation_mm"] / annual_precip_mean)
        if annual_precip_mean
        else 0.0
    )
    if driest_ratio >= 0.8 and rainfall_cv < 20:
        drought_risk = "Bajo"
    elif driest_ratio >= 0.6:
        drought_risk = "Moderado"
    else:
        drought_risk = "Alto"

    # Simplified frost screening using mean monthly minimum temperature.
    if len(frost_months) <= 1:
        frost_risk = "Bajo"
    elif len(frost_months) <= 3:
        frost_risk = "Moderado"
    else:
        frost_risk = "Alto"

    return {
        "annual_precip_mean": annual_precip_mean,
        "wettest_year": {
            "year": int(wettest_year["year"]),
            "value": float(wettest_year["precipitation_mm"]),
        },
        "driest_year": {
            "year": int(driest_year["year"]),
            "value": float(driest_year["precipitation_mm"]),
        },
        "annual_temp_mean": annual_temp_mean,
        "frost_months": frost_months,
        "rainfall_seasonality": rainfall_seasonality,
        "rainfall_cv": rainfall_cv,
        "water_stability": water_stability,
        "drought_risk": drought_risk,
        "frost_risk": frost_risk,
    }


