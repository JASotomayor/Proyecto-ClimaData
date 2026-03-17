"""scripts/04_fetch_ndvi.py

Pre-compute multianual NDVI median from Sentinel-2 L2A and save:
  - data/trebolares/processed/ndvi_median.npz   (numpy arrays, loaded by app)
  - data/trebolares/processed/ndvi_median.png   (static image with legend)

Run once from the project root:
    python scripts/04_fetch_ndvi.py

The app then loads the .npz instantly without any network call.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

# ── Fix PROJ before any rasterio import ───────────────────────────────────────
import importlib.util as _ilu
_spec = _ilu.find_spec("rasterio")
if _spec and _spec.submodule_search_locations:
    _p = Path(list(_spec.submodule_search_locations)[0]) / "proj_data"
    if (_p / "proj.db").exists():
        os.environ["PROJ_DATA"] = str(_p)
        os.environ["PROJ_LIB"]  = str(_p)

import rasterio
import rasterio.io
from rasterio.mask import mask as rio_mask
from rasterio.transform import array_bounds, from_bounds as transform_from_bounds
from rasterio.warp import (
    Resampling,
    calculate_default_transform,
    reproject,
    transform_bounds,
)

import planetary_computer
import pystac_client
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shapely_transform
from pyproj import Transformer

from src.farm import load_default_farm
from src.satellite import _utm_epsg, _read_band_to_grid   # reuse helpers

# ── Config ────────────────────────────────────────────────────────────────────
START_YEAR    = 2018
END_YEAR      = 2024
MAX_CLOUD_PCT = 20
MAX_WORKERS   = 8       # parallel scene downloads
OUT_DIR       = ROOT / "data" / "trebolares" / "processed"
NPZ_PATH      = OUT_DIR / "ndvi_median.npz"
PNG_PATH      = OUT_DIR / "ndvi_median.png"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _query_items(bbox: tuple, start_year: int, end_year: int, max_cloud: int):
    print("Conectando a Planetary Computer STAC…")
    client = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    date_ranges = []
    for yr in range(start_year, end_year + 1):
        date_ranges.append(f"{yr}-11-01/{yr}-12-31")
        date_ranges.append(f"{yr + 1}-01-01/{yr + 1}-03-31")

    all_items = []
    for dr in date_ranges:
        try:
            search = client.search(
                collections=["sentinel-2-l2a"],
                bbox=list(bbox),
                datetime=dr,
                query={"eo:cloud_cover": {"lt": max_cloud}},
                max_items=500,
            )
            items = list(search.items())
            all_items.extend(items)
            print(f"  {dr}: {len(items)} escenas")
        except Exception as exc:
            print(f"  {dr}: error ({exc})")

    seen: set[str] = set()
    unique = [i for i in all_items if not (i.id in seen or seen.add(i.id))]  # type: ignore
    print(f"Total escenas únicas: {len(unique)}")
    return unique


def _build_ndvi_stack(items, dst_transform, dst_width, dst_height, crs_utm):
    def _read_scene(item):
        try:
            b04_url = item.assets["B04"].href
            b08_url = item.assets["B08"].href
        except KeyError:
            return None
        b04 = _read_band_to_grid(b04_url, dst_transform, dst_width, dst_height, crs_utm)
        b08 = _read_band_to_grid(b08_url, dst_transform, dst_width, dst_height, crs_utm)
        if b04 is None or b08 is None:
            return None
        denom = b08 + b04
        return np.where(denom > 0, (b08 - b04) / denom, np.nan)

    scenes = []
    total = len(items)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_read_scene, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            idx = futures[future]
            result = future.result()
            if result is not None:
                scenes.append(result)
            done = len(scenes)
            print(f"  Escenas leídas: {done}/{total}", end="\r", flush=True)
    print()
    return scenes


def _save_png(ndvi_wgs84, lats, lons, coordinates, n_scenes, png_path):
    """Save a publication-quality PNG with colorbar and polygon border."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        from matplotlib.patches import Patch
    except ImportError:
        print("matplotlib no instalado — se omite la generación de PNG.")
        return

    # Normalize P2–P98
    valid = ndvi_wgs84[~np.isnan(ndvi_wgs84)]
    p2, p98 = np.percentile(valid, 2), np.percentile(valid, 98)
    arr_norm = np.clip((ndvi_wgs84 - p2) / max(p98 - p2, 1e-6), 0, 1)

    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    im = ax.imshow(
        arr_norm,
        extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        origin="lower",
        cmap="RdYlGn",
        vmin=0, vmax=1,
        aspect="auto",
        interpolation="bilinear",
    )

    # Polygon border
    poly_lons = [c[0] for c in coordinates] + [coordinates[0][0]]
    poly_lats = [c[1] for c in coordinates] + [coordinates[0][1]]
    ax.plot(poly_lons, poly_lats, color="white", linewidth=1.8, zorder=3)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Potencial relativo", fontsize=10)
    cbar.set_ticks([0, 0.5, 1])
    cbar.set_ticklabels(["Bajo", "Medio", "Alto"])

    ax.set_xlabel("Longitud", fontsize=8)
    ax.set_ylabel("Latitud",  fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_facecolor("#1A2433")
    fig.patch.set_facecolor("#F7F6F1")

    ax.set_title(
        f"Variabilidad espacial · Potencial relativo NDVI\n"
        f"Mediana Sentinel-2 L2A · nov–mar {START_YEAR}–{END_YEAR} · "
        f"{n_scenes} escenas · 10 m",
        fontsize=9, pad=8,
    )

    plt.tight_layout()
    plt.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"PNG guardado: {png_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    farm = load_default_farm()
    if farm is None:
        print("ERROR: No se encontró el KML de la finca.")
        sys.exit(1)

    bbox        = farm.bbox
    coordinates = farm.coordinates

    # 1. Query STAC
    items = _query_items(bbox, START_YEAR, END_YEAR, MAX_CLOUD_PCT)
    if not items:
        print("Sin escenas disponibles.")
        sys.exit(1)

    # 2. UTM output grid
    epsg      = _utm_epsg(bbox)
    crs_utm   = f"EPSG:{epsg}"
    resolution = 10

    utm_left, utm_bottom, utm_right, utm_top = transform_bounds(
        "EPSG:4326", crs_utm, *bbox
    )
    dst_width  = max(1, int((utm_right - utm_left)   / resolution))
    dst_height = max(1, int((utm_top   - utm_bottom) / resolution))
    dst_transform = transform_from_bounds(
        utm_left, utm_bottom, utm_right, utm_top, dst_width, dst_height
    )
    print(f"Grid UTM: {dst_width}×{dst_height} px  ({dst_width*10}×{dst_height*10} m)")

    # 3. Read scenes in parallel
    print(f"Descargando {len(items)} escenas con {MAX_WORKERS} workers…")
    scenes = _build_ndvi_stack(items, dst_transform, dst_width, dst_height, crs_utm)
    if not scenes:
        print("No se pudo leer ninguna escena.")
        sys.exit(1)
    print(f"Escenas válidas: {len(scenes)}")

    # 4. Median
    ndvi_median = np.nanmedian(np.stack(scenes, axis=0), axis=0)

    # 5. Clip to polygon (UTM)
    print("Recortando al polígono KML…")
    tr        = Transformer.from_crs("EPSG:4326", crs_utm, always_xy=True)
    poly_utm  = shapely_transform(tr.transform, Polygon([(lo, la) for lo, la in coordinates]))

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", height=dst_height, width=dst_width,
            count=1, dtype="float64", crs=crs_utm,
            transform=dst_transform, nodata=np.nan,
        ) as ds:
            ds.write(ndvi_median, 1)
            clipped_arr, clip_transform = rio_mask(
                ds, [mapping(poly_utm)], crop=True, nodata=np.nan, filled=True
            )

    ndvi_clipped                = clipped_arr[0]
    clip_height, clip_width     = ndvi_clipped.shape

    # 6. Reproject to WGS84
    print("Reproyectando a WGS84…")
    cl, cb, cr, ct = array_bounds(clip_height, clip_width, clip_transform)
    wgs_transform, wgs_width, wgs_height = calculate_default_transform(
        crs_utm, "EPSG:4326", clip_width, clip_height,
        left=cl, bottom=cb, right=cr, top=ct,
    )
    ndvi_wgs84 = np.full((wgs_height, wgs_width), np.nan, dtype="float64")
    reproject(
        source=ndvi_clipped, destination=ndvi_wgs84,
        src_transform=clip_transform, src_crs=crs_utm,
        dst_transform=wgs_transform, dst_crs="EPSG:4326",
        resampling=Resampling.bilinear,
        src_nodata=np.nan, dst_nodata=np.nan,
    )

    # 7. Extract coordinate arrays (flip to S→N)
    lons = np.array([wgs_transform.c + (i + 0.5) * wgs_transform.a for i in range(wgs_width)])
    lats = np.array([wgs_transform.f + (j + 0.5) * wgs_transform.e for j in range(wgs_height)])
    ndvi_wgs84 = np.flipud(ndvi_wgs84)
    lats       = lats[::-1]

    # 8. Save NPZ
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        NPZ_PATH,
        ndvi=ndvi_wgs84, lats=lats, lons=lons,
        n_scenes=np.array(len(scenes)),
        start_year=np.array(START_YEAR),
        end_year=np.array(END_YEAR),
    )
    print(f"NPZ guardado: {NPZ_PATH}  ({NPZ_PATH.stat().st_size // 1024} KB)")

    # 9. Save PNG with legend
    _save_png(ndvi_wgs84, lats, lons, coordinates, len(scenes), PNG_PATH)

    print("\nListo. Ejecutá la app — el mapa carga instantáneamente.")


if __name__ == "__main__":
    main()
