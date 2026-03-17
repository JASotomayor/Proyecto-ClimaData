from __future__ import annotations

from statistics import mean, pstdev
from typing import Any, TypedDict

import requests
from src.config import (
    LOCAL_RELIEF_OFFSET_DEGREES,
    OPENTOPOGRAPHY_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
)
from src.farm import FarmGeometry, build_farm_sampling_points
from src.utils import GeoPoint

TERRAIN_METHOD_NOTE = (
    "La napa freatica no puede confirmarse solo con fuentes online. "
    "Este indicador usa elevacion relativa local como aproximacion simple de drenaje."
)
TERRAIN_FALLBACK_NOTE = (
    "La napa freatica no puede confirmarse solo con internet. "
    "La arquitectura queda preparada para sumar modelos de elevacion o capas hidrologicas mas adelante."
)


class TerrainSummary(TypedDict, total=False):
    """Terrain and drainage interpretation returned to the UI."""

    available: bool
    elevation_m: float
    local_relief_range_m: float
    local_relief_std_m: float
    center_vs_neighbors_m: float
    relief_class: str
    drainage_risk: str
    interpretation: str
    method_note: str
    sampled_points: int
    error: str


class FarmTerrainCell(TypedDict):
    """Single internal farm sampling cell for relative topographic reading."""

    sample_id: str
    lat: float
    lon: float
    elevation_m: float
    elevation_delta_m: float
    relative_position: str
    relative_potential: str


class FarmTerrainSummary(TypedDict, total=False):
    """Lot-scale terrain summary derived from internal sampling points."""

    available: bool
    farm_name: str
    sampled_points: int
    mean_elevation_m: float
    elevation_range_m: float
    elevation_std_m: float
    lowland_share_pct: float
    crest_share_pct: float
    preferred_share_pct: float
    method_note: str
    interpretation: str
    cells: list[FarmTerrainCell]
    error: str


def _build_neighbor_grid(point: GeoPoint) -> list[tuple[float, float]]:
    offset = LOCAL_RELIEF_OFFSET_DEGREES
    latitudes = [point.lat - offset, point.lat, point.lat + offset]
    longitudes = [point.lon - offset, point.lon, point.lon + offset]
    return [(lat, lon) for lat in latitudes for lon in longitudes]


def _validate_elevation_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the elevation API payload and return raw results."""
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("La API de elevacion no devolvio resultados para el punto consultado.")
    return results


def fetch_elevation_grid(point: GeoPoint) -> list[dict[str, Any]]:
    """Fetch elevation for the center point and a small surrounding grid."""
    locations = "|".join(f"{lat},{lon}" for lat, lon in _build_neighbor_grid(point))
    response = requests.get(
        OPENTOPOGRAPHY_BASE_URL,
        params={"locations": locations},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("La API de elevacion devolvio una respuesta JSON invalida.") from exc
    return _validate_elevation_payload(payload)


def fetch_elevation_locations(locations: tuple[tuple[float, float], ...]) -> list[dict[str, Any]]:
    """Fetch elevation for an arbitrary tuple of lat/lon locations."""
    if not locations:
        raise ValueError("No hay puntos de muestreo para consultar elevacion.")
    response = requests.get(
        OPENTOPOGRAPHY_BASE_URL,
        params={"locations": "|".join(f"{lat},{lon}" for lat, lon in locations)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("La API de elevacion devolvio una respuesta JSON invalida.") from exc
    return _validate_elevation_payload(payload)


def _extract_elevations(results: list[dict[str, Any]]) -> tuple[float, list[float]]:
    """Extract center elevation and available neighbors without losing grid position."""
    if len(results) < 9:
        raise ValueError(
            "La API de elevacion devolvio menos puntos de los esperados para el entorno local."
        )

    center_result = results[4]
    center_elevation = center_result.get("elevation")
    if center_elevation is None:
        raise ValueError("La API de elevacion no devolvio cota para el punto central.")

    neighbor_elevations: list[float] = []
    for index, item in enumerate(results[:9]):
        if index == 4:
            continue
        elevation = item.get("elevation")
        if elevation is not None:
            neighbor_elevations.append(float(elevation))

    if len(neighbor_elevations) < 4:
        raise ValueError(
            "La API de elevacion devolvio muy pocos vecinos validos para estimar relieve local."
        )

    return float(center_elevation), neighbor_elevations


def _classify_relief(local_range: float) -> str:
    """Map local elevation range to a coarse relief class."""
    if local_range < 5:
        return "Plano a muy plano"
    if local_range < 15:
        return "Suavemente ondulado"
    return "Relieve mas marcado"


def _interpret_drainage(local_range: float, center_delta: float) -> tuple[str, str]:
    """Infer a simple drainage risk and interpretation from local relief."""
    if local_range < 5 and center_delta <= -1.0:
        return (
            "Alto",
            "Punto algo mas bajo que el entorno inmediato dentro de una superficie muy plana.",
        )
    if local_range < 10:
        return (
            "Moderado",
            "Entorno de poca pendiente; conviene revisar bajos, huellas de agua y cunetas.",
        )
    return (
        "Bajo a moderado",
        "Hay algo mas de energia de relieve, lo que reduce la probabilidad de acumulacion local.",
    )


def _build_unavailable_terrain_summary(error_message: str) -> TerrainSummary:
    """Return a stable terrain fallback payload."""
    return {
        "available": False,
        "error": error_message,
        "method_note": TERRAIN_FALLBACK_NOTE,
    }


def _classify_relative_position(
    elevation_m: float,
    mean_elevation_m: float,
    elevation_std_m: float,
) -> str:
    """Classify a sampled point according to relative topographic position."""
    if elevation_std_m <= 0:
        return "Posicion media"
    z_score = (elevation_m - mean_elevation_m) / elevation_std_m
    if z_score <= -0.8:
        return "Bajo relativo"
    if z_score >= 0.8:
        return "Loma relativa"
    return "Posicion media"


def _classify_relative_potential(relative_position: str) -> str:
    """Map relative topographic position to a prudent potential class."""
    if relative_position == "Bajo relativo":
        return "Potencial relativo limitado"
    if relative_position == "Loma relativa":
        return "Potencial relativo intermedio"
    return "Potencial relativo preferente"


def _interpret_farm_relief(
    elevation_range_m: float,
    lowland_share_pct: float,
    crest_share_pct: float,
) -> str:
    """Build a short interpretation for lot-scale topographic behavior."""
    if elevation_range_m < 2.0:
        if lowland_share_pct >= 25:
            return (
                "Lote muy plano con presencia apreciable de bajos relativos; conviene priorizar "
                "revision de anegamiento, escurrimiento y estabilidad del piso."
            )
        return (
            "Lote muy plano y relativamente uniforme; la variabilidad topografica interna parece baja "
            "bajo esta aproximacion inicial."
        )
    if lowland_share_pct >= 25:
        return (
            "La variabilidad interna sugiere sectores mas bajos que pueden concentrar agua o presentar "
            "condiciones mas restrictivas en campanas humedas."
        )
    if crest_share_pct >= 25:
        return (
            "La variabilidad interna sugiere sectores mas altos o descargados; conviene revisar si esas "
            "zonas pierden estabilidad hidrica en campanas secas."
        )
    return (
        "El lote muestra una transicion topografica moderada con predominio de posiciones medias, "
        "que son un buen punto de partida para definir ambientes relativos."
    )


def get_terrain_summary(point: GeoPoint) -> TerrainSummary:
    """Estimate local relief and a basic water accumulation signal."""
    try:
        results = fetch_elevation_grid(point)
        center_elevation, neighbor_elevations = _extract_elevations(results)
        sampled_elevations = neighbor_elevations + [center_elevation]
        local_range = max(sampled_elevations) - min(sampled_elevations)
        neighbor_mean = mean(neighbor_elevations)
        center_delta = center_elevation - neighbor_mean
        relief_class = _classify_relief(local_range)
        drainage_risk, interpretation = _interpret_drainage(local_range, center_delta)

        return {
            "available": True,
            "elevation_m": round(center_elevation, 1),
            "local_relief_range_m": round(local_range, 1),
            "local_relief_std_m": round(pstdev(sampled_elevations), 1),
            "center_vs_neighbors_m": round(center_delta, 1),
            "relief_class": relief_class,
            "drainage_risk": drainage_risk,
            "interpretation": interpretation,
            "method_note": TERRAIN_METHOD_NOTE,
            "sampled_points": len(sampled_elevations),
        }
    except Exception as exc:  # pragma: no cover
        return _build_unavailable_terrain_summary(str(exc))


def get_farm_terrain_summary(farm_geometry: FarmGeometry) -> FarmTerrainSummary:
    """Estimate internal lot-scale topographic variability from a simple sampling grid."""
    try:
        sampling_points = build_farm_sampling_points(farm_geometry)
        raw_results = fetch_elevation_locations(
            tuple((point.lat, point.lon) for point in sampling_points)
        )
        if len(raw_results) != len(sampling_points):
            raise ValueError("La API de elevacion devolvio menos resultados que puntos muestreados.")

        elevations: list[float] = []
        for result in raw_results:
            elevation = result.get("elevation")
            if elevation is None:
                raise ValueError("La API de elevacion no devolvio cota en todos los puntos del lote.")
            elevations.append(float(elevation))

        mean_elevation_m = mean(elevations)
        elevation_std_m = pstdev(elevations) if len(elevations) > 1 else 0.0
        elevation_range_m = max(elevations) - min(elevations)
        cells: list[FarmTerrainCell] = []
        for index, (point, elevation_m) in enumerate(
            zip(sampling_points, elevations, strict=False),
            start=1,
        ):
            relative_position = _classify_relative_position(
                elevation_m=elevation_m,
                mean_elevation_m=mean_elevation_m,
                elevation_std_m=elevation_std_m,
            )
            cells.append(
                {
                    "sample_id": f"M{index}",
                    "lat": round(point.lat, 6),
                    "lon": round(point.lon, 6),
                    "elevation_m": round(elevation_m, 1),
                    "elevation_delta_m": round(elevation_m - mean_elevation_m, 1),
                    "relative_position": relative_position,
                    "relative_potential": _classify_relative_potential(relative_position),
                }
            )

        lowland_share_pct = (
            sum(cell["relative_position"] == "Bajo relativo" for cell in cells)
            / len(cells)
            * 100
        )
        crest_share_pct = (
            sum(cell["relative_position"] == "Loma relativa" for cell in cells)
            / len(cells)
            * 100
        )
        preferred_share_pct = (
            sum(cell["relative_potential"] == "Potencial relativo preferente" for cell in cells)
            / len(cells)
            * 100
        )

        return {
            "available": True,
            "farm_name": farm_geometry.name,
            "sampled_points": len(cells),
            "mean_elevation_m": round(mean_elevation_m, 1),
            "elevation_range_m": round(elevation_range_m, 1),
            "elevation_std_m": round(elevation_std_m, 1),
            "lowland_share_pct": round(lowland_share_pct, 1),
            "crest_share_pct": round(crest_share_pct, 1),
            "preferred_share_pct": round(preferred_share_pct, 1),
            "method_note": (
                "Lectura inicial del lote basada en una grilla simple de elevacion dentro del poligono. "
                "Sirve para detectar posiciones relativas, no para definir ambientes finales."
            ),
            "interpretation": _interpret_farm_relief(
                elevation_range_m=elevation_range_m,
                lowland_share_pct=lowland_share_pct,
                crest_share_pct=crest_share_pct,
            ),
            "cells": cells,
        }
    except Exception as exc:  # pragma: no cover
        return {
            "available": False,
            "error": str(exc),
            "method_note": (
                "No se pudo construir la lectura interna del lote. La arquitectura queda preparada "
                "para seguir con relieve, ambientes y potencial relativo."
            ),
        }
