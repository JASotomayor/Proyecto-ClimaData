"""Fetch multianual Sentinel-2 NDVI from Microsoft Planetary Computer.

Uses rasterio for direct COG reads — no stackstac, no dask, no xarray —
which avoids version-compatibility issues between those libraries.

Algorithm
---------
1. Query Planetary Computer STAC for Sentinel-2 L2A items in the
   growing season (Nov–Mar) with cloud cover < threshold.
2. For each item, read bands B04 (Red) and B08 (NIR) via rasterio,
   reprojecting on-the-fly to a common UTM 10-m grid over the bbox.
3. Compute per-scene NDVI = (B08 − B04) / (B08 + B04).
4. Take the pixel-wise nanmedian across all scenes.
5. Clip to the farm polygon, reproject to WGS84, and return plain
   numpy arrays ready for Plotly.
"""
from __future__ import annotations

import os

import numpy as np
import streamlit as st

# OSGeo4W does not propagate PROJ_DATA to child processes (e.g. Streamlit).
# Set it here so pyproj and rasterio.warp can find the datum grids.
if not os.environ.get("PROJ_DATA") and not os.environ.get("PROJ_LIB"):
    _OSGEO_PROJ = r"C:\OSGeo4W\share\proj"
    if os.path.isdir(_OSGEO_PROJ):
        os.environ["PROJ_DATA"] = _OSGEO_PROJ
        os.environ["PROJ_LIB"]  = _OSGEO_PROJ


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _utm_epsg(bbox: tuple[float, float, float, float]) -> int:
    """Return the UTM EPSG code for the centre of the bounding box."""
    min_lon, min_lat, max_lon, max_lat = bbox
    centre_lon = (min_lon + max_lon) / 2.0
    centre_lat = (min_lat + max_lat) / 2.0
    zone = int((centre_lon + 180.0) / 6.0) + 1
    return 32700 + zone if centre_lat < 0 else 32600 + zone


def _read_band_to_grid(
    url: str,
    dst_transform,
    dst_width: int,
    dst_height: int,
    dst_crs: str,
) -> "np.ndarray | None":
    """Read one Sentinel-2 band COG, warping to the output UTM grid."""
    try:
        import rasterio
        from rasterio.warp import reproject, Resampling

        with rasterio.open(url) as src:
            out = np.zeros((dst_height, dst_width), dtype="float64")
            reproject(
                source=rasterio.band(src, 1),
                destination=out,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=0,        # Sentinel-2 L2A: 0 = nodata
                dst_nodata=np.nan,
            )
            return out
    except Exception:
        return None


# ─── Public API ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_ndvi_median(
    coordinates: tuple[tuple[float, float], ...],
    bbox: tuple[float, float, float, float],
    start_year: int = 2018,
    end_year: int = 2024,
    max_cloud_pct: int = 20,
    max_scenes: int = 40,
) -> dict:
    """Return multianual NDVI median clipped to the farm polygon.

    Returns
    -------
    dict with keys:
        ``ndvi``     – np.ndarray 2D float64, NaN outside polygon,
                       row-0 = southernmost latitude.
        ``lats``     – np.ndarray 1D, increasing south → north.
        ``lons``     – np.ndarray 1D, increasing west → east.
        ``n_scenes`` – number of scenes included in the median.
        ``error``    – str if something failed, else None.
    """
    # ── 0. Import dependencies ────────────────────────────────────────────────
    try:
        import rasterio
        from rasterio.warp import (
            reproject, Resampling,
            calculate_default_transform,
            transform_bounds,
        )
        from rasterio.transform import from_bounds as transform_from_bounds
        from rasterio.mask import mask as rio_mask
        import rasterio.io
        import planetary_computer
        import pystac_client
        from shapely.geometry import Polygon, mapping
        from shapely.ops import transform as shapely_transform
        from pyproj import Transformer
    except ImportError as exc:
        return {"error": f"Dependencia faltante: {exc}"}

    # ── 1. Query STAC ─────────────────────────────────────────────────────────
    try:
        client = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )
    except Exception as exc:
        return {"error": f"No se pudo conectar a Planetary Computer: {exc}"}

    date_ranges: list[str] = []
    for yr in range(start_year, end_year + 1):
        date_ranges.append(f"{yr}-11-01/{yr}-12-31")
        date_ranges.append(f"{yr + 1}-01-01/{yr + 1}-03-31")

    all_items: list = []
    for dr in date_ranges:
        try:
            search = client.search(
                collections=["sentinel-2-l2a"],
                bbox=list(bbox),
                datetime=dr,
                query={"eo:cloud_cover": {"lt": max_cloud_pct}},
                max_items=500,
            )
            all_items.extend(list(search.items()))
        except Exception:
            pass

    seen: set[str] = set()
    unique_items = [
        item for item in all_items
        if not (item.id in seen or seen.add(item.id))  # type: ignore[func-returns-value]
    ]

    if not unique_items:
        return {
            "error": (
                "Sin imágenes Sentinel-2 disponibles para este lote y período. "
                "Verificá la cobertura o reducí el umbral de nubosidad."
            )
        }

    # ── 2. Define output UTM grid ─────────────────────────────────────────────
    epsg      = _utm_epsg(bbox)
    crs_utm   = f"EPSG:{epsg}"
    resolution = 10  # metres

    try:
        utm_left, utm_bottom, utm_right, utm_top = transform_bounds(
            "EPSG:4326", crs_utm, *bbox
        )
    except Exception as exc:
        return {"error": f"Error al proyectar bbox a UTM: {exc}"}

    dst_width  = max(1, int((utm_right  - utm_left)   / resolution))
    dst_height = max(1, int((utm_top    - utm_bottom)  / resolution))
    dst_transform = transform_from_bounds(
        utm_left, utm_bottom, utm_right, utm_top,
        dst_width, dst_height,
    )

    # ── 3. Read scenes ────────────────────────────────────────────────────────
    ndvi_scenes: list[np.ndarray] = []
    items_to_use = unique_items[:max_scenes]

    for item in items_to_use:
        try:
            b04_url = item.assets["B04"].href
            b08_url = item.assets["B08"].href
        except KeyError:
            continue

        b04 = _read_band_to_grid(b04_url, dst_transform, dst_width, dst_height, crs_utm)
        b08 = _read_band_to_grid(b08_url, dst_transform, dst_width, dst_height, crs_utm)

        if b04 is None or b08 is None:
            continue

        denom = b08 + b04
        ndvi  = np.where(denom > 0, (b08 - b04) / denom, np.nan)
        ndvi_scenes.append(ndvi)

    if not ndvi_scenes:
        return {"error": "No se pudo leer ninguna escena (errores de descarga)."}

    # ── 4. Median across scenes ───────────────────────────────────────────────
    ndvi_stack  = np.stack(ndvi_scenes, axis=0)
    ndvi_median = np.nanmedian(ndvi_stack, axis=0)

    # ── 5. Clip to farm polygon (in UTM) ──────────────────────────────────────
    try:
        tr = Transformer.from_crs("EPSG:4326", crs_utm, always_xy=True)
        poly_wgs84 = Polygon([(lon, lat) for lon, lat in coordinates])
        poly_utm   = shapely_transform(tr.transform, poly_wgs84)

        with rasterio.io.MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff",
                height=dst_height,
                width=dst_width,
                count=1,
                dtype="float64",
                crs=crs_utm,
                transform=dst_transform,
                nodata=np.nan,
            ) as ds:
                ds.write(ndvi_median, 1)
                clipped_arr, clip_transform = rio_mask(
                    ds,
                    [mapping(poly_utm)],
                    crop=True,
                    nodata=np.nan,
                    filled=True,
                )

        ndvi_clipped = clipped_arr[0]
        clip_height, clip_width = ndvi_clipped.shape
    except Exception as exc:
        return {"error": f"Error al recortar al polígono: {exc}"}

    # ── 6. Reproject clipped raster to WGS84 ─────────────────────────────────
    try:
        wgs_transform, wgs_width, wgs_height = calculate_default_transform(
            crs_utm, "EPSG:4326",
            clip_width, clip_height,
            transform=clip_transform,
        )
        ndvi_wgs84 = np.full((wgs_height, wgs_width), np.nan, dtype="float64")
        reproject(
            source=ndvi_clipped,
            destination=ndvi_wgs84,
            src_transform=clip_transform,
            src_crs=crs_utm,
            dst_transform=wgs_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    except Exception as exc:
        return {"error": f"Error al reproyectar a WGS84: {exc}"}

    # ── 7. Extract coordinate arrays ─────────────────────────────────────────
    # Affine: (a=pix_width, b=0, c=west, d=0, e=-pix_height, f=north)
    lons = np.array([
        wgs_transform.c + (i + 0.5) * wgs_transform.a
        for i in range(wgs_width)
    ], dtype="float64")
    lats = np.array([
        wgs_transform.f + (j + 0.5) * wgs_transform.e
        for j in range(wgs_height)
    ], dtype="float64")   # decreasing: north → south

    # Flip to south → north (row-0 = southernmost) for Plotly
    ndvi_wgs84 = np.flipud(ndvi_wgs84)
    lats       = lats[::-1]

    return {
        "ndvi":     ndvi_wgs84,
        "lats":     lats,
        "lons":     lons,
        "n_scenes": len(ndvi_scenes),
        "error":    None,
    }
