from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.config import DEFAULT_LAT, DEFAULT_LON, DEFAULT_POINT_NAME


@dataclass(frozen=True)
class GeoPoint:
    """Simple immutable geographic point."""

    lat: float
    lon: float
    source: str = "default"
    label: str = DEFAULT_POINT_NAME


def get_logger(name: str) -> logging.Logger:
    """Return a module logger with a simple default configuration."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    return logging.getLogger(name)


def format_lat_lon(lat: float, lon: float, decimals: int = 6) -> str:
    """Format latitude and longitude for display."""
    return f"{lat:.{decimals}f}, {lon:.{decimals}f}"


def initialize_session_state() -> None:
    """Create base session values for the selected point."""
    import streamlit as st

    if "selected_point" not in st.session_state:
        st.session_state.selected_point = GeoPoint(
            lat=DEFAULT_LAT,
            lon=DEFAULT_LON,
            source="default",
            label=DEFAULT_POINT_NAME,
        )
    if "point_message" not in st.session_state:
        st.session_state.point_message = None
    if "selected_farm" not in st.session_state:
        st.session_state.selected_farm = None
    if "farm_message" not in st.session_state:
        st.session_state.farm_message = None


def load_local_css(css_path: str) -> None:
    """Load a local CSS file if present."""
    import streamlit as st

    css_file = Path(css_path)
    if css_file.exists():
        st.markdown(
            f"<style>{css_file.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def update_selected_point(point: GeoPoint, message: str | None = None) -> None:
    """Persist the selected point in Streamlit session state."""
    import streamlit as st

    st.session_state.selected_point = point
    st.session_state.point_message = message


def update_selected_farm(farm: object | None, message: str | None = None) -> None:
    """Persist the selected farm geometry in Streamlit session state."""
    import streamlit as st

    st.session_state.selected_farm = farm
    st.session_state.farm_message = message
