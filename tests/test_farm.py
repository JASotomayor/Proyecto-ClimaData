from __future__ import annotations

from src.farm import build_farm_sampling_points, parse_farm_kml, point_in_polygon

_SQUARE_KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Lote Norte</name>
    <Placemark>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -60.0000,-33.0000,0
              -60.0000,-33.0100,0
              -59.9900,-33.0100,0
              -59.9900,-33.0000,0
              -60.0000,-33.0000,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""


def test_parse_farm_kml_extracts_geometry_and_centroid() -> None:
    farm = parse_farm_kml(_SQUARE_KML, file_name="lote.kml")
    assert farm.name == "Lote Norte"
    assert farm.point_count == 4
    assert farm.area_ha > 0
    assert farm.perimeter_m > 0
    assert -33.01 < farm.centroid.lat < -33.0
    assert -60.0 < farm.centroid.lon < -59.99


def test_parse_farm_kml_rejects_invalid_geometry() -> None:
    invalid = b"<kml><Document><Placemark><Point><coordinates>-60,-33,0</coordinates></Point></Placemark></Document></kml>"
    try:
        parse_farm_kml(invalid, file_name="point_only.kml")
    except ValueError as exc:
        assert "poligono" in str(exc).lower()
    else:
        raise AssertionError("Se esperaba un ValueError por KML sin polígono.")


def test_point_in_polygon_and_sampling_points() -> None:
    large_kml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>
        -60.0000,-33.0000,0 -60.0000,-33.0200,0
        -59.9800,-33.0200,0 -59.9800,-33.0000,0
        -60.0000,-33.0000,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>"""
    farm = parse_farm_kml(large_kml, file_name="sampling.kml")
    assert point_in_polygon(-59.99, -33.01, farm.coordinates)
    assert not point_in_polygon(-60.05, -33.01, farm.coordinates)
    points = build_farm_sampling_points(farm, approx_point_count=9)
    assert len(points) >= 4
    assert any(
        abs(p.lat - farm.centroid.lat) < 1e-6 and abs(p.lon - farm.centroid.lon) < 1e-6
        for p in points
    )
