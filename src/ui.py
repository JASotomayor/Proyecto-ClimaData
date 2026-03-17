from __future__ import annotations

from typing import Any

import folium
import streamlit as st
from streamlit_folium import st_folium

from src.config import APP_ICON, APP_LAYOUT, APP_TITLE, MAP_ZOOM
from src.farm import FarmGeometry
from src.utils import GeoPoint, format_lat_lon, initialize_session_state, load_local_css


# ─── Brand assets ─────────────────────────────────────────────────────────────

# Lote Prime isotipo — "Prime Lot Shield"
# Pentágono tipo escudo: parche de lote + silueta Prime (hombros anchos, vértice inferior)
# Barra horizontal: hilera de cultivo + visor Prime (guiño sutil)
# Nodo central: centroide GPS + núcleo Prime
_BRAND_SVG = (
    '<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="40" height="40" rx="9" fill="#EF9645"/>'
    '<polygon points="9,8 31,8 36,21 20,36 4,21"'
    ' fill="rgba(30,57,83,0.08)" stroke="#1E3953"'
    ' stroke-width="2.5" stroke-linejoin="round"/>'
    '<rect x="13" y="14" width="14" height="3.5" rx="1.75" fill="#1E3953"/>'
    '<circle cx="20" cy="26" r="2.8" fill="#1E3953"/>'
    '</svg>'
)

# Three horizontal bars, middle one shorter for visual refinement
_HAMBURGER_SVG = (
    '<svg width="20" height="14" viewBox="0 0 20 14" fill="none">'
    '<rect y="0"  width="20" height="2.5" rx="1.25" fill="white"/>'
    '<rect y="6"  width="14" height="2.5" rx="1.25" fill="white" opacity="0.8"/>'
    '<rect y="11.5" width="20" height="2.5" rx="1.25" fill="white"/>'
    '</svg>'
)

# Nav icons for drawer
_NAV_ICONS: dict[str, str] = {
    "Finca":       "&#x2302;",   # ⌂
    "Clima":       "&#x2601;",   # ☁
    "Cultivos":    "&#x273F;",   # ✿
    "Producción":  "&#x25B2;",   # ▲
    "Metodología": "&#x2261;",   # ≡
}


# ─── Page init ────────────────────────────────────────────────────────────────

def initialize_page() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)
    initialize_session_state()
    load_local_css("assets/custom.css")


# ─── Desktop sidebar ──────────────────────────────────────────────────────────

def render_sidebar(farm_geometry: FarmGeometry, start_year: int, end_year: int) -> None:
    """Desktop sidebar: brand block + farm summary."""
    coord = format_lat_lon(farm_geometry.centroid.lat, farm_geometry.centroid.lon)
    with st.sidebar:
        # Brand block
        st.markdown(
            '<div class="ms-sidebar-brand">'
            + _BRAND_SVG
            + '<div>'
            '<div class="ms-sb-name">LOTE PRIME</div>'
            '<div class="ms-sb-sub">Inteligencia agronómica</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        # Farm meta (compact, below brand)
        st.markdown(
            f'<div class="ms-sb-meta">'
            f'<div class="ms-sb-meta-farm">{farm_geometry.name}</div>'
            f'<div class="ms-sb-meta-detail">{farm_geometry.area_ha:.0f} ha &nbsp;·&nbsp; {coord}</div>'
            f'<div class="ms-sb-meta-detail">{start_year} – {end_year}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="ms-sidebar-nav-label">SECCIONES</div>',
            unsafe_allow_html=True,
        )


# ─── Mobile header + slide-in drawer ─────────────────────────────────────────

def render_mobile_topbar(
    farm_geometry: FarmGeometry,
    start_year: int,
    end_year: int,
    current_page: str = "Finca",
    nav_pages: list[str] | None = None,
) -> None:
    """Universal nav bar + temporary slide-in drawer.

    Everything lives inside a single st.components.v1.html() iframe so there
    are no issues with Streamlit's sanitiser, React wrapper stacking contexts,
    or cross-iframe DOM manipulation.

    Open:  hamburger click → iframe expands to fullscreen via window.frameElement
    Close: overlay click or nav selection → iframe shrinks back to topbar height
    Nav:   window.parent.location.href = ?p=<page>  (same-tab, no new tab)
    """
    import streamlit.components.v1 as components

    if nav_pages is None:
        nav_pages = ["Finca", "Clima", "Cultivos", "Producción", "Metodología"]

    name  = farm_geometry.name or "Finca"
    area  = f"{farm_geometry.area_ha:.0f} ha"
    coord = format_lat_lon(farm_geometry.centroid.lat, farm_geometry.centroid.lon)

    nav_items_html = "".join(
        '<button class="nav-item{active}" onclick="navigate(\'{p}\')">'
        '<span class="nav-icon">{icon}</span>'
        '<span class="nav-label">{p}</span>'
        '</button>'.format(
            active=" active" if p == current_page else "",
            p=p,
            icon=_NAV_ICONS.get(p, "&#x25CF;"),
        )
        for p in nav_pages
    )

    html = """<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:transparent;font-family:'Montserrat','Segoe UI',sans-serif;overflow:hidden}
.topbar{display:flex;align-items:center;gap:.85rem;background:#1E3953;border-radius:12px;padding:.8rem 1rem;height:56px}
.hamburger{display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:8px;border:none;background:rgba(255,255,255,.08);cursor:pointer;transition:background .15s;flex-shrink:0;-webkit-tap-highlight-color:transparent}
.hamburger:hover,.hamburger:active{background:rgba(255,255,255,.18)}
.topbar-content{flex:1;min-width:0}
.topbar-name{font-size:.95rem;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.topbar-meta{font-size:.72rem;color:#8FA8BB;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.50);z-index:998;cursor:pointer}
body.open .overlay{display:block}
.drawer{position:fixed;top:0;left:-300px;width:275px;height:100%;background:#1E3953;z-index:999;transition:left .32s cubic-bezier(.4,0,.2,1);padding:1.4rem 1.25rem 2rem;overflow-y:auto;display:flex;flex-direction:column;box-shadow:4px 0 24px rgba(0,0,0,.28)}
body.open .drawer{left:0}
.drawer-brand{display:flex;align-items:center;gap:.85rem;padding-bottom:1rem;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:.75rem}
.brand-name{font-size:.95rem;font-weight:700;color:#fff;letter-spacing:.04em}
.brand-sub{font-size:.62rem;font-weight:500;color:#8FA8BB;text-transform:uppercase;letter-spacing:.06em;margin-top:.1rem}
.drawer-nav{display:flex;flex-direction:column;gap:.15rem;margin-top:.25rem}
.nav-item{display:flex;align-items:center;gap:.75rem;padding:.7rem .85rem;border-radius:9px;color:#8FA8BB;font-size:.9rem;font-weight:500;background:transparent;border:none;width:100%;text-align:left;cursor:pointer;transition:background .15s,color .15s;border-left:3px solid transparent;font-family:'Montserrat',sans-serif}
.nav-item:hover{background:rgba(255,255,255,.07);color:#fff}
.nav-item.active{background:rgba(239,150,69,.13);color:#EF9645;font-weight:700;border-left-color:#EF9645}
.nav-icon{font-size:1rem;width:1.4rem;text-align:center;flex-shrink:0}
.nav-label{flex:1}
</style>
</head><body>
<div class="topbar">
  <button class="hamburger" onclick="openDrawer()" aria-label="Menú">HAMBURGER_SVG</button>
  <div class="topbar-content">
    <div class="topbar-name">FARM_NAME</div>
    <div class="topbar-meta">FARM_META</div>
  </div>
</div>
<div class="overlay" onclick="closeDrawer()"></div>
<div class="drawer">
  <div class="drawer-brand">BRAND_SVG<div><div class="brand-name">LOTE PRIME</div><div class="brand-sub">Inteligencia agronómica</div></div></div>
  <nav class="drawer-nav">NAV_ITEMS</nav>
</div>
<script>
(function(){
  var fr=window.frameElement;
  function setSize(full){
    if(!fr)return;
    fr.style.cssText=full
      ?'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:9999;border:none;background:transparent;'
      :'height:56px;width:100%;border:none;display:block;background:transparent;';
  }
  function openDrawer(){document.body.classList.add('open');setSize(true);}
  function closeDrawer(cb){
    document.body.classList.remove('open');
    setSize(false);
    if(cb)setTimeout(cb,320);
  }
  function navigate(page){
    closeDrawer(function(){
      window.parent.location.href='?p='+encodeURIComponent(page);
    });
  }
  window.openDrawer=openDrawer;
  window.closeDrawer=closeDrawer;
  window.navigate=navigate;
  setSize(false);
})();
</script>
</body></html>""".replace(
        "HAMBURGER_SVG", _HAMBURGER_SVG
    ).replace(
        "FARM_NAME", name
    ).replace(
        "FARM_META", f"{area}&nbsp;·&nbsp;{coord}"
    ).replace(
        "BRAND_SVG", _BRAND_SVG
    ).replace(
        "NAV_ITEMS", nav_items_html
    )

    components.html(html, height=56, scrolling=False)


def _build_basemap(point: GeoPoint, farm_geometry: FarmGeometry | None = None) -> folium.Map:
    fmap = folium.Map(
        location=[point.lat, point.lon],
        zoom_start=MAP_ZOOM,
        control_scale=True,
        tiles="CartoDB positron",
    )
    folium.TileLayer("OpenStreetMap", name="OSM").add_to(fmap)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Satélite",
    ).add_to(fmap)
    if farm_geometry:
        polygon_coordinates = [[lat, lon] for lon, lat in farm_geometry.coordinates]
        folium.Polygon(
            locations=polygon_coordinates,
            color="#1E3953",
            weight=2,
            fill=True,
            fill_color="#EF9645",
            fill_opacity=0.12,
            tooltip=f"{farm_geometry.name} · {farm_geometry.area_ha:.0f} ha",
        ).add_to(fmap)
        fmap.fit_bounds(polygon_coordinates, max_zoom=14)
    folium.CircleMarker(
        location=[point.lat, point.lon],
        radius=4,
        color="#EF9645",
        fill=True,
        fill_color="#EF9645",
        fill_opacity=1.0,
        tooltip=f"Centroide · {format_lat_lon(point.lat, point.lon)}",
    ).add_to(fmap)
    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap


def render_map_card(point: GeoPoint, farm_geometry: FarmGeometry | None = None) -> None:
    """Render the farm polygon map."""
    st_folium(
        _build_basemap(point, farm_geometry=farm_geometry),
        width=None,
        height=300,
        use_container_width=True,
        key="farm_map",
        returned_objects=[],
    )


def render_farm_tab(
    farm_geometry: FarmGeometry | None,
    point: GeoPoint,
    climate_bundle: dict[str, Any] | None = None,
) -> None:
    """Render farm geometry metrics."""
    if not farm_geometry:
        return
    st.markdown(
        '<span class="ms-section-header">Geometría del lote</span>',
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    cols[0].metric("Superficie", f"{farm_geometry.area_ha:.1f} ha")
    cols[1].metric("Perímetro", f"{farm_geometry.perimeter_m:.0f} m")
    st.caption(
        f"Centroide operativo: {format_lat_lon(point.lat, point.lon)} · "
        "el análisis climático y agronómico se calcula sobre este punto."
    )


def render_methodology_tab(estimable: list[str], not_confirmable: list[str]) -> None:
    """Render methodological scope and limitations."""
    import pandas as pd

    # ── Fuentes de datos ──────────────────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Fuentes de datos</span>',
        unsafe_allow_html=True,
    )
    sources_df = pd.DataFrame([
        ("NASA POWER", "ERA5-reanalysis", "~55 km", "Clima diario histórico (precipitación, temperatura mín/máx/media)"),
        ("SoilGrids v2.0", "ISRIC", "250 m", "Propiedades de suelo estimadas globalmente (textura, pH, C orgánico, CEC)"),
        ("OpenTopoData", "SRTM", "30 m", "Elevación digital para inferir relieve local y riesgo de drenaje"),
        ("MAGyP/SIIA", "Estimaciones Agrícolas", "Departamento", "Rendimientos y superficie regional (Maracó, La Pampa)"),
    ], columns=["Fuente", "Modelo/Origen", "Resolución", "Uso"])
    st.dataframe(sources_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Modelo agronómico ─────────────────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Modelo agronómico</span>',
        unsafe_allow_html=True,
    )
    notes = [
        "**ETo:** Hargreaves-Samani FAO Paper 56 con factor 0.88 calibrado INTA Anguil (temperatura mín/máx).",
        "**ETc = ETo × Kc** — coeficientes de cultivo FAO Paper 56 tabla 12, por etapa fenológica.",
        "**Balance hídrico:** precipitación bruta − ETc por etapa; calendario fenológico fijo sin almacenaje de suelo.",
        "**Score 0–100:** componentes hídrico ciclo completo + etapas críticas (mayor peso) + térmico + completitud de datos.",
        "El análisis expresa ajuste agronómico relativo histórico. No predice rendimiento absoluto.",
    ]
    for note in notes:
        st.markdown(f"- {note}")

    st.divider()

    # ── Correlación score–rendimiento ─────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Correlación score–rendimiento (Pearson r)</span>',
        unsafe_allow_html=True,
    )
    corr_df = pd.DataFrame([
        ("Maíz temprano",      0.43),
        ("Trigo",              0.52),
        ("Soja de primera",    0.46),
        ("Soja de segunda",    0.39),
    ], columns=["Cultivo", "r"])
    st.dataframe(corr_df, use_container_width=True, hide_index=True)
    st.caption(
        "r ≈ 0.4–0.5 es consistente con un modelo hídrico simplificado sin almacenaje de suelo. "
        "Calculado sobre años con datos comunes MAGyP/SIIA + scores agroclimáticos (Departamento Maracó)."
    )

    st.divider()

    # ── Alcance ───────────────────────────────────────────────────────────────
    st.markdown(
        '<span class="ms-section-header">Alcance: qué se puede y qué no se puede saber desde fuentes abiertas</span>',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Se puede estimar**")
        for item in estimable:
            st.markdown(f"- {item}")
    with col2:
        st.markdown("**No se puede confirmar con precisión solo online**")
        for item in not_confirmable:
            st.markdown(f"- {item}")
