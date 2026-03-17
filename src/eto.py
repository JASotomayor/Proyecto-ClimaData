from __future__ import annotations

from math import acos, cos, pi, sin, sqrt, tan

import pandas as pd

GSC = 0.0820
MJ_TO_EVAP_EQUIVALENT = 0.408
HS_REGIONAL_CALIBRATION = 0.88   # Factor INTA Anguil para La Pampa (pampa húmeda/subhúmeda)
MIN_VALID_TEMPERATURE_C = -50.0
MAX_VALID_TEMPERATURE_C = 65.0
MIN_VALID_LATITUDE_DEG = -90.0
MAX_VALID_LATITUDE_DEG = 90.0

ETO_METHODS = {
    "hargreaves_samani": {
        "label": "Hargreaves-Samani FAO-56 · factor regional INTA Anguil 0.88",
        "note": (
            "ETo calculada por el método Hargreaves-Samani (Allen et al., FAO Paper 56, 1998) "
            "usando Tmax, Tmin y radiación extraterrestre (Ra) función de latitud y día del año. "
            "Se aplica un factor de calibración regional de 0.88 derivado de la validación de "
            "INTA EEA Anguil para la región pampeana húmeda/subhúmeda (La Pampa central), "
            "que corrige la sobreestimación sistemática del método estándar en condiciones de "
            "alta humedad relativa invernal. Sin ese ajuste el método estándar sobreestima "
            "ETo un 9–28% en los meses fríos respecto al lisímetro de referencia de Anguil. "
            "Se usa Hargreaves-Samani porque los datos NASA POWER no proveen radiación solar "
            "medida, viento ni humedad con la precisión necesaria para Penman-Monteith en "
            "series largas de punto."
        ),
    },
    "penman_monteith_fao56": {
        "label": "Penman-Monteith FAO-56",
        "note": (
            "Método FAO-56 de referencia (Allen et al., 1998). Requiere radiación solar, "
            "humedad relativa y velocidad del viento con cobertura temporal completa."
        ),
    },
}


def _validate_latitude(latitude_deg: float) -> None:
    """Validate latitude bounds for FAO radiation calculations."""
    if not (MIN_VALID_LATITUDE_DEG <= latitude_deg <= MAX_VALID_LATITUDE_DEG):
        raise ValueError("La latitud esta fuera de rango para calcular ETo.")


def _inverse_relative_distance_earth_sun(day_of_year: int) -> float:
    return 1 + 0.033 * cos((2 * pi / 365) * day_of_year)


def _solar_declination(day_of_year: int) -> float:
    return 0.409 * sin((2 * pi / 365) * day_of_year - 1.39)


def _sunset_hour_angle(latitude_rad: float, solar_declination: float) -> float:
    solar_term = -tan(latitude_rad) * tan(solar_declination)
    bounded_term = min(1.0, max(-1.0, solar_term))
    return acos(bounded_term)


def extraterrestrial_radiation(latitude_deg: float, day_of_year: int) -> float:
    """Compute extraterrestrial radiation in MJ m-2 day-1."""
    _validate_latitude(latitude_deg)
    if not 1 <= day_of_year <= 366:
        raise ValueError("El dia del ano esta fuera de rango para el calculo de radiacion.")

    latitude_rad = latitude_deg * pi / 180
    dr = _inverse_relative_distance_earth_sun(day_of_year)
    delta = _solar_declination(day_of_year)
    ws = _sunset_hour_angle(latitude_rad, delta)
    radiation = (
        (24 * 60 / pi)
        * GSC
        * dr
        * (
            ws * sin(latitude_rad) * sin(delta)
            + cos(latitude_rad) * cos(delta) * sin(ws)
        )
    )
    return max(radiation, 0.0)


def _radiation_to_evaporation_equivalent(radiation_mj_m2_day: float) -> float:
    """Convert radiation in MJ m-2 day-1 to evaporation equivalent in mm day-1."""
    return radiation_mj_m2_day * MJ_TO_EVAP_EQUIVALENT


def _validate_temperature_inputs(
    temp_mean_c: float,
    temp_min_c: float,
    temp_max_c: float,
) -> bool:
    """Check whether daily temperatures are physically usable for ETo."""
    temperatures = [temp_mean_c, temp_min_c, temp_max_c]
    if any(pd.isna(value) for value in temperatures):
        return False
    if any(value < MIN_VALID_TEMPERATURE_C or value > MAX_VALID_TEMPERATURE_C for value in temperatures):
        return False
    if temp_max_c < temp_min_c:
        return False
    return True


def calculate_hargreaves_eto(
    temp_mean_c: float,
    temp_min_c: float,
    temp_max_c: float,
    latitude_deg: float,
    day_of_year: int,
) -> float | None:
    """Compute daily reference evapotranspiration using Hargreaves-Samani."""
    if not _validate_temperature_inputs(temp_mean_c, temp_min_c, temp_max_c):
        return None

    thermal_range = max(temp_max_c - temp_min_c, 0.0)
    if thermal_range == 0:
        return 0.0

    radiation_mj_m2_day = extraterrestrial_radiation(latitude_deg, day_of_year)
    radiation_mm_day = _radiation_to_evaporation_equivalent(radiation_mj_m2_day)
    eto = 0.0023 * radiation_mm_day * (temp_mean_c + 17.8) * sqrt(thermal_range) * HS_REGIONAL_CALIBRATION
    return round(max(eto, 0.0), 3)


def _supports_penman_monteith(climate_daily: pd.DataFrame) -> bool:
    """Check if the dataset includes the minimum extra variables for FAO-56 PM."""
    required_columns = {"solar_radiation_mj_m2", "relative_humidity_pct", "wind_speed_m_s"}
    return required_columns.issubset(climate_daily.columns)


def resolve_eto_method(
    climate_daily: pd.DataFrame,
    preferred_method: str = "auto",
) -> tuple[str, bool]:
    """Resolve the ETo method to use, returning the chosen method and fallback flag."""
    if preferred_method == "auto":
        if _supports_penman_monteith(climate_daily):
            return "penman_monteith_fao56", False
        return "hargreaves_samani", True

    if preferred_method == "penman_monteith_fao56" and not _supports_penman_monteith(climate_daily):
        return "hargreaves_samani", True

    return preferred_method, False


def get_eto_method_label(method_key: str) -> str:
    """Return a user-facing label for the selected ETo method."""
    return ETO_METHODS.get(method_key, {}).get("label", method_key)


def get_eto_method_note(method_key: str, used_as_fallback: bool = False) -> str:
    """Return a short note describing the selected ETo method."""
    base_note = ETO_METHODS.get(method_key, {}).get("note", "Metodo ETo no documentado.")
    if used_as_fallback:
        return f"{base_note} En esta corrida se uso como fallback prudente."
    return base_note


def compute_reference_eto_daily(
    climate_daily: pd.DataFrame,
    latitude_deg: float,
    preferred_method: str = "auto",
) -> pd.DataFrame:
    """Add daily ETo and method metadata to a daily climate dataframe."""
    if climate_daily.empty:
        raise ValueError("No hay datos climaticos diarios para calcular ETo.")
    if "date" not in climate_daily.columns:
        raise ValueError("La serie climatica no incluye la columna 'date'.")

    method_key, used_as_fallback = resolve_eto_method(climate_daily, preferred_method)
    requested_method = method_key
    implementation_fallback = False
    if method_key != "hargreaves_samani":
        method_key = "hargreaves_samani"
        used_as_fallback = True
        implementation_fallback = True

    eto_daily = climate_daily.copy()
    eto_daily["day_of_year"] = eto_daily["date"].dt.dayofyear
    eto_daily["temperature_range_c"] = (
        eto_daily["temp_max_c"] - eto_daily["temp_min_c"]
    ).round(2)
    eto_daily["eto_valid"] = eto_daily.apply(
        lambda row: _validate_temperature_inputs(
            float(row["temp_mean_c"]) if not pd.isna(row["temp_mean_c"]) else row["temp_mean_c"],
            float(row["temp_min_c"]) if not pd.isna(row["temp_min_c"]) else row["temp_min_c"],
            float(row["temp_max_c"]) if not pd.isna(row["temp_max_c"]) else row["temp_max_c"],
        ),
        axis=1,
    )
    eto_daily["eto_mm_day"] = eto_daily.apply(
        lambda row: calculate_hargreaves_eto(
            temp_mean_c=float(row["temp_mean_c"]),
            temp_min_c=float(row["temp_min_c"]),
            temp_max_c=float(row["temp_max_c"]),
            latitude_deg=latitude_deg,
            day_of_year=int(row["day_of_year"]),
        )
        if row["eto_valid"]
        else pd.NA,
        axis=1,
    )
    eto_daily["eto_method_requested"] = preferred_method
    eto_daily["eto_method"] = method_key
    eto_daily["eto_method_label"] = get_eto_method_label(method_key)
    method_note = get_eto_method_note(
        method_key,
        used_as_fallback=used_as_fallback,
    )
    if implementation_fallback:
        method_note = (
            f"{method_note} Penman-Monteith FAO-56 queda reservado para una iteracion futura."
        )
    eto_daily["eto_method_note"] = method_note
    eto_daily["eto_method_requested_resolved"] = requested_method
    return eto_daily
