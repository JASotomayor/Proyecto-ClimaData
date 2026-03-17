from __future__ import annotations

import io
from typing import Any, TypedDict

import numpy as np
import requests
from PIL import Image

from src.config import REQUEST_TIMEOUT_SECONDS, SOILGRIDS_BASE_URL
from src.utils import GeoPoint

try:
    import pyproj as _pyproj
    _PYPROJ_AVAILABLE = True
except ImportError:
    _PYPROJ_AVAILABLE = False

SOIL_PROPERTIES = ["sand", "silt", "clay", "phh2o", "soc", "cec", "cfvo"]
SOIL_SOURCE = "SoilGrids (ISRIC)"
SOIL_SOURCE_NOTE = (
    "SoilGrids 250m v2.0 (ISRIC, 2020) · horizonte 0–5 cm · valor medio predictivo · "
    "resolución espacial ~250 m. Estimación interpolada a partir de perfil de suelos globales "
    "y capas ambientales; no reemplaza análisis de suelo propio. En lotes con variabilidad "
    "edáfica marcada o suelos atípicos para la región, contrastar con muestreo en campo."
)

_WCS_BASE_URL = "https://maps.isric.org/mapserv"
_WCS_IGH_PROJ = "+proj=igh +datum=WGS84 +units=m +no_defs"
_WCS_CRS_URN = "urn:ogc:def:crs:EPSG::152160"
_WCS_NODATA = -32768
_WCS_DELTA_M = 5000   # half-side of bounding box in metres


class SoilSummary(TypedDict, total=False):
    """Normalized soil summary used by the UI."""

    available: bool
    source: str
    source_note: str
    texture_class: str
    sand_pct: float | None
    silt_pct: float | None
    clay_pct: float | None
    ph: float | None
    ph_unit: str
    organic_carbon: float | None
    organic_carbon_unit: str
    cec: float | None
    cec_unit: str
    coarse_fragments: float | None
    coarse_fragments_unit: str
    fraction_unit: str
    observations: list[str]
    error: str


def estimate_texture_class(
    sand_pct: float | None,
    silt_pct: float | None,
    clay_pct: float | None,
) -> str:
    """Estimate a simplified textural class from soil fractions."""
    if sand_pct is None or silt_pct is None or clay_pct is None:
        return "No disponible"
    if clay_pct >= 40:
        return "Arcillosa"
    if sand_pct >= 70 and clay_pct < 15:
        return "Arenosa"
    if silt_pct >= 50 and clay_pct < 27:
        return "Franca limosa"
    if 20 <= clay_pct < 35 and 25 <= sand_pct <= 55:
        return "Franca arcillosa"
    return "Franca"


def _build_unavailable_soil_summary(error_message: str) -> SoilSummary:
    """Return a stable fallback response for UI consumption."""
    return {
        "available": False,
        "source": SOIL_SOURCE,
        "source_note": SOIL_SOURCE_NOTE,
        "error": error_message,
        "observations": [
            "No se pudo consultar la fuente de suelos en este momento.",
            "La arquitectura queda preparada para sumar capas de INTA o servicios locales mas adelante.",
        ],
    }


# ─── WCS-based fetching ────────────────────────────────────────────────────────

def _latlon_to_igh(lat: float, lon: float) -> tuple[float, float]:
    """Convert WGS84 lat/lon to Interrupted Goode Homolosine coordinates."""
    if not _PYPROJ_AVAILABLE:
        raise ImportError("pyproj no esta disponible para convertir coordenadas WCS.")
    transformer = _pyproj.Transformer.from_crs(
        "EPSG:4326", _WCS_IGH_PROJ, always_xy=True
    )
    x, y = transformer.transform(lon, lat)
    return float(x), float(y)


def _extract_tiff_from_wcs_multipart(content: bytes) -> bytes | None:
    """Extract the GeoTIFF payload from a WCS multipart/mixed response."""
    parts = content.split(b"--wcs")
    for part in parts:
        if b"image/tiff" in part:
            idx = part.find(b"\r\n\r\n")
            if idx >= 0:
                return part[idx + 4 :].rstrip(b"\r\n--")
    return None


def _fetch_wcs_center_value(prop: str, x: float, y: float) -> float | None:
    """Fetch a single SoilGrids property value at position (x, y) via WCS 1.1.1."""
    bbox = f"{x - _WCS_DELTA_M},{y - _WCS_DELTA_M},{x + _WCS_DELTA_M},{y + _WCS_DELTA_M}"
    params = {
        "map": f"/map/{prop}.map",
        "SERVICE": "WCS",
        "VERSION": "1.1.1",
        "REQUEST": "GetCoverage",
        "IDENTIFIER": f"{prop}_0-5cm_mean",
        "BoundingBox": f"{bbox},{_WCS_CRS_URN}",
        "FORMAT": "image/tiff",
        "GridBaseCRS": _WCS_CRS_URN,
        "GridOffsets": "250,-250",
    }
    r = requests.get(_WCS_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    r.raise_for_status()

    tif_data = _extract_tiff_from_wcs_multipart(r.content)
    if tif_data is None:
        return None

    arr = np.array(Image.open(io.BytesIO(tif_data)))
    cy, cx = arr.shape[0] // 2, arr.shape[1] // 2
    val = arr[cy, cx]
    return None if int(val) == _WCS_NODATA else float(val)


def fetch_soilgrids_wcs(lat: float, lon: float) -> dict[str, float | None]:
    """Fetch all soil properties for a point using the SoilGrids WCS endpoint."""
    x, y = _latlon_to_igh(lat, lon)
    raw: dict[str, float | None] = {}
    for prop in SOIL_PROPERTIES:
        raw[prop] = _fetch_wcs_center_value(prop, x, y)
    return raw


# ─── REST-based fetching (original, kept as optional fallback) ─────────────────

def _validate_soilgrids_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("SoilGrids no devolvio el bloque 'properties' esperado.")
    layers = properties.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("SoilGrids no devolvio capas de suelo para el punto consultado.")
    return layers


def _extract_property_value_rest(
    payload: dict[str, Any],
    property_name: str,
) -> tuple[float | None, str | None]:
    layers = _validate_soilgrids_payload(payload)
    for layer in layers:
        if layer.get("name") != property_name:
            continue
        depths = layer.get("depths", [])
        if not depths:
            return None, None
        values = depths[0].get("values", {})
        unit = layer.get("unit_measure", {}).get("mapped_units")
        mean_value = values.get("mean")
        return (
            float(mean_value) if mean_value is not None else None,
            str(unit) if unit is not None else None,
        )
    return None, None


def _fetch_soilgrids_rest(lat: float, lon: float) -> dict[str, Any]:
    params: list[tuple[str, str | float]] = [("lat", lat), ("lon", lon)]
    params.extend(("property", p) for p in SOIL_PROPERTIES)
    params.extend([("depth", "0-5cm"), ("value", "mean")])
    r = requests.get(SOILGRIDS_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    r.raise_for_status()
    payload = r.json()
    _validate_soilgrids_payload(payload)
    return payload


# ─── Normalization helpers ─────────────────────────────────────────────────────

def _normalize_soil_fraction(raw_value: float | None) -> float | None:
    """Convert soil fractions from g/kg to percent."""
    if raw_value is None:
        return None
    return round(raw_value / 10, 1)


def _normalize_ph(raw_value: float | None) -> float | None:
    if raw_value is None:
        return None
    return round(raw_value / 10, 1) if raw_value > 14 else round(raw_value, 1)


def _build_soil_observations(
    sand_pct: float | None,
    silt_pct: float | None,
    clay_pct: float | None,
    ph_value: float | None,
    coarse_fragments_pct: float | None,
) -> list[str]:
    observations: list[str] = []
    if clay_pct is not None and clay_pct >= 35:
        observations.append(
            "Fracción arcilla elevada (≥35%): capacidad de retención hídrica alta, pero "
            "con riesgo de anegamiento transitorio en posiciones bajas, dificultad de "
            "laboreo con alta humedad y posible limitación al desarrollo radicular por "
            "resistencia mecánica al secado."
        )
    if sand_pct is not None and sand_pct >= 70:
        observations.append(
            "Textura arenosa (arena ≥70%): baja capacidad de retención de agua útil "
            "(AWC estimada <80 mm/m). Los déficits en etapas críticas se expresan con "
            "mayor velocidad que en suelos francos; la fertilización nitrogenada puede "
            "tener mayor riesgo de lixiviación."
        )
    if silt_pct is not None and silt_pct >= 55:
        observations.append(
            "Predominio de limo (≥55%): susceptibilidad al sellado superficial y a la "
            "formación de costra. Monitorear estructura e infiltración ante lluvias "
            "intensas o laboreo en condiciones inadecuadas de humedad."
        )
    if ph_value is not None and ph_value < 5.5:
        observations.append(
            f"pH superficial ácido ({ph_value}): posible limitación de disponibilidad "
            "de P, Mo y B; riesgo de toxicidad de Al y Mn en horizontes subsuperficiales. "
            "Evaluar encalado."
        )
    if ph_value is not None and ph_value > 7.8:
        observations.append(
            f"pH superficial alcalino ({ph_value}): puede comprometer disponibilidad "
            "de Fe, Mn, Zn y B. En suelos con carbonatos activos, revisar micronutrientes "
            "para soja y maíz."
        )
    if coarse_fragments_pct is not None and coarse_fragments_pct >= 15:
        observations.append(
            f"Fragmentos gruesos estimados en {coarse_fragments_pct:.0f}%: reduce el "
            "volumen efectivo de suelo y la capacidad de almacenamiento hídrico. "
            "Verificar en campo."
        )
    if not observations:
        observations.append(
            "Sin limitaciones edáficas marcadas en la capa 0–5 cm según la estimación "
            "global. Perfil consistente con suelos agrícolas productivos de la región."
        )
    observations.append(
        "Estimación SoilGrids 250m v2.0 — horizonte 0–5 cm. Validar con análisis "
        "de suelo propio antes de decisiones de manejo."
    )
    return observations


# ─── Public entry point ────────────────────────────────────────────────────────

def get_soil_summary(point: GeoPoint) -> SoilSummary:
    """Build a resilient soil summary — tries WCS first, REST as fallback."""
    # --- Try WCS (maps.isric.org) ---
    if _PYPROJ_AVAILABLE:
        try:
            raw = fetch_soilgrids_wcs(point.lat, point.lon)
            sand_pct = _normalize_soil_fraction(raw.get("sand"))
            silt_pct = _normalize_soil_fraction(raw.get("silt"))
            clay_pct = _normalize_soil_fraction(raw.get("clay"))
            coarse_fragments_pct = _normalize_soil_fraction(raw.get("cfvo"))
            ph_value = _normalize_ph(raw.get("phh2o"))
            soc_raw = raw.get("soc")
            cec_raw = raw.get("cec")

            if all(v is None for v in (sand_pct, silt_pct, clay_pct, ph_value)):
                raise ValueError("WCS respondio pero no entrego propiedades utiles.")

            # WCS SOC unit is dg/kg → divide by 10 for g/kg
            soc_gkg = round(soc_raw / 10, 1) if soc_raw is not None else None
            # WCS CEC unit is mmol(c)/kg → divide by 10 for cmolc/kg
            cec_cmol = round(cec_raw / 10, 1) if cec_raw is not None else None

            return {
                "available": True,
                "source": SOIL_SOURCE,
                "source_note": SOIL_SOURCE_NOTE,
                "texture_class": estimate_texture_class(sand_pct, silt_pct, clay_pct),
                "sand_pct": sand_pct,
                "silt_pct": silt_pct,
                "clay_pct": clay_pct,
                "ph": ph_value,
                "ph_unit": "pH",
                "organic_carbon": soc_gkg,
                "organic_carbon_unit": "g/kg",
                "cec": cec_cmol,
                "cec_unit": "cmolc/kg",
                "coarse_fragments": coarse_fragments_pct,
                "coarse_fragments_unit": "%",
                "fraction_unit": "%",
                "observations": _build_soil_observations(
                    sand_pct=sand_pct,
                    silt_pct=silt_pct,
                    clay_pct=clay_pct,
                    ph_value=ph_value,
                    coarse_fragments_pct=coarse_fragments_pct,
                ),
            }
        except Exception:
            pass  # fall through to REST

    # --- Fallback: REST API (rest.isric.org) ---
    try:
        payload = _fetch_soilgrids_rest(point.lat, point.lon)
        sand_raw, sand_unit = _extract_property_value_rest(payload, "sand")
        silt_raw, silt_unit = _extract_property_value_rest(payload, "silt")
        clay_raw, clay_unit = _extract_property_value_rest(payload, "clay")
        ph_raw, ph_unit = _extract_property_value_rest(payload, "phh2o")
        soc_raw, soc_unit = _extract_property_value_rest(payload, "soc")
        cec_raw, cec_unit = _extract_property_value_rest(payload, "cec")
        coarse_raw, coarse_unit = _extract_property_value_rest(payload, "cfvo")

        sand_pct = _normalize_soil_fraction(sand_raw)
        silt_pct = _normalize_soil_fraction(silt_raw)
        clay_pct = _normalize_soil_fraction(clay_raw)
        coarse_fragments_pct = _normalize_soil_fraction(coarse_raw)
        ph_value = _normalize_ph(ph_raw)

        if all(v is None for v in (sand_pct, silt_pct, clay_pct, ph_value, soc_raw, cec_raw)):
            raise ValueError("SoilGrids REST respondio pero no entrego propiedades utiles.")

        return {
            "available": True,
            "source": SOIL_SOURCE,
            "source_note": SOIL_SOURCE_NOTE,
            "texture_class": estimate_texture_class(sand_pct, silt_pct, clay_pct),
            "sand_pct": sand_pct,
            "silt_pct": silt_pct,
            "clay_pct": clay_pct,
            "ph": ph_value,
            "ph_unit": ph_unit or "pH",
            "organic_carbon": round(float(soc_raw), 1) if soc_raw is not None else None,
            "organic_carbon_unit": soc_unit or "g/kg",
            "cec": round(float(cec_raw), 1) if cec_raw is not None else None,
            "cec_unit": cec_unit or "cmolc/kg",
            "coarse_fragments": coarse_fragments_pct,
            "coarse_fragments_unit": coarse_unit or "%",
            "fraction_unit": sand_unit or silt_unit or clay_unit or "g/kg",
            "observations": _build_soil_observations(
                sand_pct=sand_pct,
                silt_pct=silt_pct,
                clay_pct=clay_pct,
                ph_value=ph_value,
                coarse_fragments_pct=coarse_fragments_pct,
            ),
        }
    except Exception as exc:
        return _build_unavailable_soil_summary(str(exc))
