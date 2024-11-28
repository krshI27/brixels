import folium
import streamlit as st
from streamlit_folium import st_folium
import numpy as np

st.set_page_config(
    page_title="Brixels",
    page_icon="🧱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

with open("static/style.css") as css:
    st.markdown(
        f"<style>{css.read()}</style>",
        unsafe_allow_html=True,
    )
def meters_to_latlon_shift(lat, lon, shift_meters):
    # Earth's radius in meters
    R = 6378137
    # Coordinate offsets in radians
    d_lat = shift_meters / R
    d_lon = shift_meters / (R * np.cos(np.pi * lat / 180))
    # Offset positions in decimal degrees
    lat_shift = d_lat * 180 / np.pi
    lon_shift = d_lon * 180 / np.pi
    return lat_shift, lon_shift

icon_path = "./static/brick_top.png"
location_coords = np.array([39.949610, -75.150282])
if "zoom_level" not in st.session_state:
    st.session_state["zoom_level"] = 16
def main():

    # center on Liberty Bell, add marker
    m = folium.Map(location=location_coords, zoom_start=st.session_state.zoom_level, crs="EPSG3857")
    shift = 10 * st.session_state.zoom_level

    lat_shift, lon_shift = meters_to_latlon_shift(location_coords[0], location_coords[1], shift)
    marker_coords = location_coords + np.array([lat_shift, -lon_shift])
    folium.Marker(
        location_coords, icon=folium.features.CustomIcon(icon_image=icon_path, icon_size=(50, 50))).add_to(m)
    folium.Marker(
        marker_coords, icon=folium.features.CustomIcon(icon_image=icon_path, icon_size=(50, 50))).add_to(m)
    st_data = st_folium(m)
    st.session_state["zoom_level"] = st_data["zoom"]

if __name__ == "__main__":
    main()
