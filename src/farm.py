from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from src.config import FARM_KML_PATH
from src.utils import GeoPoint

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class FarmGeometry:
    """Parsed farm polygon and its basic geometric summary."""

    name: str
    coordinates: tuple[tuple[float, float], ...]
    centroid: GeoPoint
    area_ha: float
    perimeter_m: float
    bbox: tuple[float, float, float, float]
    point_count: int


def point_in_polygon(
    lon: float,
    lat: float,
    polygon_coordinates: tuple[tuple[float, float], ...],
) -> bool:
    """Return whether a lon/lat point lies inside a polygon ring."""
    inside = False
    for index, (lon1, lat1) in enumerate(polygon_coordinates):
        lon2, lat2 = polygon_coordinates[(index + 1) % len(polygon_coordinates)]
        intersects = ((lat1 > lat) != (lat2 > lat)) and (
            lon < (lon2 - lon1) * (lat - lat1) / ((lat2 - lat1) or 1e-12) + lon1
        )
        if intersects:
            inside = not inside
    return inside


def _extract_kml_name(root: ET.Element) -> str:
    """Extract a human-readable name from the KML when possible."""
    for element in root.iter():
        if element.tag.endswith("name") and element.text and element.text.strip():
            return element.text.strip()
    return "Finca cargada desde KML"


def _parse_coordinate_text(raw_text: str) -> tuple[tuple[float, float], ...]:
    """Parse KML coordinate text into lon/lat tuples."""
    coordinates: list[tuple[float, float]] = []
    for token in raw_text.replace("\n", " ").replace("\t", " ").split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        coordinates.append((lon, lat))

    if len(coordinates) < 3:
        raise ValueError("El KML no contiene un poligono valido con suficientes vertices.")

    if coordinates[0] == coordinates[-1]:
        coordinates = coordinates[:-1]
    if len(coordinates) < 3:
        raise ValueError("El poligono del KML queda invalido tras normalizar el anillo.")
    return tuple(coordinates)


def _project_ring_to_local_meters(
    coordinates: tuple[tuple[float, float], ...],
) -> tuple[list[tuple[float, float]], float]:
    """Project geographic coordinates to a local planar system for rough geometry."""
    mean_lat_rad = math.radians(sum(lat for _, lat in coordinates) / len(coordinates))
    projected_ring = [
        (
            EARTH_RADIUS_M * math.radians(lon) * math.cos(mean_lat_rad),
            EARTH_RADIUS_M * math.radians(lat),
        )
        for lon, lat in coordinates
    ]
    return projected_ring, mean_lat_rad


def _signed_area(projected_ring: list[tuple[float, float]]) -> float:
    """Compute polygon signed area in projected meters."""
    area = 0.0
    for index, (x1, y1) in enumerate(projected_ring):
        x2, y2 = projected_ring[(index + 1) % len(projected_ring)]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _polygon_centroid(
    coordinates: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    """Compute centroid in lon/lat using a local planar approximation."""
    projected_ring, mean_lat_rad = _project_ring_to_local_meters(coordinates)
    signed_area = _signed_area(projected_ring)
    if abs(signed_area) < 1e-9:
        mean_lon = sum(lon for lon, _ in coordinates) / len(coordinates)
        mean_lat = sum(lat for _, lat in coordinates) / len(coordinates)
        return mean_lon, mean_lat

    cx = 0.0
    cy = 0.0
    for index, (x1, y1) in enumerate(projected_ring):
        x2, y2 = projected_ring[(index + 1) % len(projected_ring)]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    cx /= 6.0 * signed_area
    cy /= 6.0 * signed_area
    centroid_lon = math.degrees(cx / (EARTH_RADIUS_M * math.cos(mean_lat_rad)))
    centroid_lat = math.degrees(cy / EARTH_RADIUS_M)
    return centroid_lon, centroid_lat


def _polygon_area_ha(
    coordinates: tuple[tuple[float, float], ...],
) -> float:
    """Approximate polygon area in hectares."""
    projected_ring, _ = _project_ring_to_local_meters(coordinates)
    area_m2 = abs(_signed_area(projected_ring))
    return area_m2 / 10_000.0


def _haversine_distance_m(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    """Compute segment distance on Earth in meters."""
    lon1_rad = math.radians(lon1)
    lat1_rad = math.radians(lat1)
    lon2_rad = math.radians(lon2)
    lat2_rad = math.radians(lat2)
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


def _polygon_perimeter_m(
    coordinates: tuple[tuple[float, float], ...],
) -> float:
    """Compute polygon perimeter in meters."""
    perimeter_m = 0.0
    for index, (lon1, lat1) in enumerate(coordinates):
        lon2, lat2 = coordinates[(index + 1) % len(coordinates)]
        perimeter_m += _haversine_distance_m(lon1, lat1, lon2, lat2)
    return perimeter_m


def _find_polygon_rings(root: ET.Element) -> list[tuple[tuple[float, float], ...]]:
    """Extract polygon outer rings from a KML document."""
    polygon_rings: list[tuple[tuple[float, float], ...]] = []
    for element in root.iter():
        if not element.tag.endswith("Polygon"):
            continue
        for ring in element.iter():
            if ring.tag.endswith("coordinates") and ring.text:
                polygon_rings.append(_parse_coordinate_text(ring.text))
    return polygon_rings


def parse_farm_kml(content: bytes, file_name: str = "finca.kml") -> FarmGeometry:
    """Parse a KML file and return the largest polygon as a farm geometry."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"No se pudo leer el KML: {file_name}.") from exc

    polygon_rings = _find_polygon_rings(root)
    if not polygon_rings:
        raise ValueError("El archivo no contiene un poligono KML utilizable.")

    selected_ring = max(polygon_rings, key=_polygon_area_ha)
    centroid_lon, centroid_lat = _polygon_centroid(selected_ring)
    centroid = GeoPoint(
        lat=centroid_lat,
        lon=centroid_lon,
        source="farm_kml",
        label="Centroide de finca",
    )
    lons = [lon for lon, _ in selected_ring]
    lats = [lat for _, lat in selected_ring]
    farm_name = _extract_kml_name(root)
    return FarmGeometry(
        name=farm_name,
        coordinates=selected_ring,
        centroid=centroid,
        area_ha=round(_polygon_area_ha(selected_ring), 1),
        perimeter_m=round(_polygon_perimeter_m(selected_ring), 1),
        bbox=(min(lons), min(lats), max(lons), max(lats)),
        point_count=len(selected_ring),
    )


def load_default_farm() -> FarmGeometry | None:
    """Load the fixed farm KML defined in config.FARM_KML_PATH.

    Returns None if the file does not exist or cannot be parsed.
    Result is cached so the file is only read once per session.
    """
    kml_path = Path(FARM_KML_PATH)
    if not kml_path.exists():
        return None
    try:
        return parse_farm_kml(kml_path.read_bytes(), file_name=kml_path.name)
    except Exception:
        return None


def build_farm_sampling_points(
    farm_geometry: FarmGeometry,
    approx_point_count: int | None = None,
) -> list[GeoPoint]:
    """Build a simple internal sampling grid for lot-scale summaries."""
    target_points = approx_point_count
    if target_points is None:
        if farm_geometry.area_ha < 30:
            target_points = 9
        elif farm_geometry.area_ha < 120:
            target_points = 16
        else:
            target_points = 25

    side_count = max(3, int(round(math.sqrt(target_points))))
    min_lon, min_lat, max_lon, max_lat = farm_geometry.bbox
    lon_step = (max_lon - min_lon) / side_count
    lat_step = (max_lat - min_lat) / side_count

    sampling_points: list[GeoPoint] = []
    seen_coordinates: set[tuple[float, float]] = set()
    for row_index in range(side_count):
        for col_index in range(side_count):
            lon = min_lon + (col_index + 0.5) * lon_step
            lat = min_lat + (row_index + 0.5) * lat_step
            if not point_in_polygon(lon, lat, farm_geometry.coordinates):
                continue
            rounded_key = (round(lat, 6), round(lon, 6))
            if rounded_key in seen_coordinates:
                continue
            seen_coordinates.add(rounded_key)
            sampling_points.append(
                GeoPoint(
                    lat=lat,
                    lon=lon,
                    source="farm_sampling",
                    label=f"Muestra {len(sampling_points) + 1}",
                )
            )

    centroid_key = (
        round(farm_geometry.centroid.lat, 6),
        round(farm_geometry.centroid.lon, 6),
    )
    if centroid_key not in seen_coordinates:
        sampling_points.append(farm_geometry.centroid)

    return sampling_points
