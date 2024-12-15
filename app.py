import json
import os
import random
import time
from dataclasses import dataclass
from urllib.request import urlopen

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3
from pyproj import CRS
from shapely import box
from shapely.geometry import Point
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval
import matplotlib.colors as mc
import matplotlib.pyplot as plt

import colorsys

os.chdir(os.path.dirname(__file__))
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
grid_size_dict = {
    1: 512000,
    2: 512000,
    3: 256000,
    4: 128000,
    5: 64000,
    6: 32000,
    7: 16000,
    8: 8000,
}
brick_size = 10
win_width = streamlit_js_eval(
    js_expressions="window.innerWidth",
    key="SCR",
)
if win_width is not None:
    map_width = win_width * 3 / 5
    map_height = win_width * 2 / 5
else:
    map_width = 100
    map_height = 100
min_zoom = 1
max_zoom = 8
CENTER_START = [0, 0]
ZOOM_START = 1
ELEVATION_FRACTION = 12800


def traverse(d):
    for key, val in d.items():
        if isinstance(val, dict):
            yield from traverse(val)
        else:
            yield val


def unpack_bounds(bounds):
    sw = bounds["_southWest"]
    ne = bounds["_northEast"]
    return sw["lat"], sw["lng"], ne["lat"], ne["lng"]


def create_grid(bounds, brick_size, map_width, map_height):
    x_min, y_min, x_max, y_max = bounds

    x_range = x_max - x_min
    y_range = y_max - y_min

    x_step = x_range / (map_width / brick_size)
    y_step = y_range / (map_height / brick_size)

    x_points = np.arange(x_min, x_max + x_step, x_step)
    y_points = np.arange(y_min, y_max + y_step, y_step)[::-1]

    grid_points = [(x, y) for x in x_points for y in y_points]
    return grid_points


if "bounds" not in st.session_state:
    st.session_state["bounds"] = {
        "_southWest": {"lat": -85.06, "lng": -180},
        "_northEast": {"lat": 85.06, "lng": 180},
    }
if "zoom" not in st.session_state:
    st.session_state["zoom"] = ZOOM_START

m = folium.Map(
    location=CENTER_START,
    zoom_start=ZOOM_START,
    min_lat=-85.06,
    max_lat=85.06,
    min_lon=-180,
    max_lon=180,
    max_bounds=True,
    min_zoom=min_zoom,
    max_zoom=max_zoom,
)
# sw = [-85.06, -180]
# ne = [85.06, 180]
# m.fit_bounds([sw, ne])

feature_group = folium.map.FeatureGroup(name="Points")


class BrickIcon:
    def __init__(self, zoom, elevation, color="#277AA2", color_shadow="#08567C"):
        self.zoom = zoom
        self.elevation = elevation
        self.color = color
        self.color_shadow = color_shadow

    def _create_square_base(self):
        return f"""<rect
            style="fill:{self.color_shadow};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            id="square_base"
            width="{self.zoom*49}"
            height="{self.zoom*49}"
            x="{self.zoom*(self.elevation+0.5)}"
            y="{self.zoom*(self.elevation+0.5)}" />"""

    def _create_square_height(self):
        return f"""<path
            style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{np.sqrt(2*((self.zoom*50)**2))};stroke-linecap:butt;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            d="M {self.zoom*25},{self.zoom*25} {self.zoom*(self.elevation+25)},{self.zoom*(self.elevation+25)}"
            id="square_height" />"""

    def _create_square_top(self):
        return f"""<rect
            style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            id="square_top"
            width="{self.zoom*49}"
            height="{self.zoom*49}"
            x="{self.zoom*0.5}"
            y="{self.zoom*0.5}" />"""

    def _create_circle_base(self):
        return f"""<circle
            style="fill:{self.color_shadow};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            id="circle_base"
            cx="{self.zoom*25}"
            cy="{self.zoom*25}"
            r="{self.zoom*14.5}" />"""

    def _create_circle_height(self):
        return f"""<path
            style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*30};stroke-linecap:butt;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            d="M {self.zoom*20},{self.zoom*20} {self.zoom*25},{self.zoom*25}"
            id="circle_height" />"""

    def _create_circle_top(self):
        return f"""<circle
            style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            id="circle_top"
            cx="{self.zoom*20}"
            cy="{self.zoom*20}"
            r="{self.zoom*14.5}" />"""

    def generate_svg(self):
        return f"""<div><svg
            version="1.1"
            id="svg1"
            xmlns="http://www.w3.org/2000/svg"
            xmlns:svg="http://www.w3.org/2000/svg">
            <defs id="defs1" />
            <g id="layer1">
                {self._create_square_base()}
                {self._create_square_height()}
                {self._create_square_top()}
                {self._create_circle_base()}
                {self._create_circle_height()}
                {self._create_circle_top()}
            </g>
        </svg></div>"""


class ColorUtils:
    @staticmethod
    def _ensure_rgb(value):
        """Convert single value to RGB tuple by repeating the value"""
        if isinstance(value, (int, float)):
            return (value, value, value)
        return value

    @staticmethod
    def to_hex(r, g=None, b=None):
        """Convert RGB values to hex color string"""
        if g is None and b is None:
            r, g, b = ColorUtils._ensure_rgb(r)
        return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

    @classmethod
    def create_color_pair(cls, value, base_range=(0, 255), shadow_factor=0.75):
        """Create a pair of colors (base, shadow) from input value"""
        # Normalize value to 0-255 range
        base_min, base_max = base_range
        normalized = (value - base_min) / (base_max - base_min) * 255

        # Create slightly lighter shadow version
        shadow = int(min(normalized * shadow_factor, 255))

        return cls.to_hex(normalized), cls.to_hex(shadow)


def adjust_lightness(color, amount=0.5):
    import colorsys

    c = colorsys.rgb_to_hls(*color)
    return colorsys.hls_to_rgb(c[0], max(0, min(1, amount * c[1])), c[2])




def scale_lightness(rgb, scale_l):
    # convert rgb to hls
    h, l, s = colorsys.rgb_to_hls(*rgb)
    # manipulate h, l, s values and return as rgb
    return colorsys.hls_to_rgb(h, min(1, l * scale_l), s=s)


def calculate_zoom_divisor(grid_size: int) -> float:
    """Calculate the zoom divisor based on grid size
    Reference:  512000m -> 15
                256000m -> 30
                128000m -> 60
    Formula: divisor = 30 * (256000/grid_size)
    """
    return 15 * (512000 / grid_size)


if not any(pd.isna([val for val in traverse(st.session_state["bounds"])])):
    grid_size = grid_size_dict[st.session_state["zoom"]]  # Use the dataclass constant
    y_min, x_min, y_max, x_max = traverse(st.session_state["bounds"])
    if x_min < -180:
        x_min = -180
    if x_max > 180:
        x_max = 180
    bounding_box = box(x_min, y_min, x_max, y_max)
    gdf = gpd.GeoDataFrame(geometry=[bounding_box], crs=CRS.from_epsg(4326))
    gdf = gdf.to_crs(epsg=3857)
    bounds = gdf.total_bounds
    layer_name = f"brixels_world_{grid_size:06d}"
    grid = gpd.read_file(
        "/data/brixels_world_512000-008000.gpkg",
        layer=layer_name,
        bbox=tuple(bounds),
    )
    grid["x"] = grid.geometry.x
    grid["y"] = grid.geometry.y

    zoom_divisor = calculate_zoom_divisor(grid_size)
    zoom = (2 ** st.session_state["zoom"]) / zoom_divisor
    # Normalize elevation data
    norm = plt.Normalize(vmin=grid["elevation"].min(), vmax=grid["elevation"].max())
    # Map elevation to colormap
    cmap = plt.cm.viridis

    # Apply colormap to elevation data
    grid[["r", "g", "b", "a"]] = grid["elevation"].apply(
        lambda x: pd.Series(cmap(norm(x)))
    )
    # Use the r, g, b values as input for create_color_pair method
    grid["color"] = grid.apply(
        lambda row: pd.Series(mc.to_hex((row["r"], row["g"], row["b"]))),
        axis=1,
    )
    grid["color_shadow"] = grid.apply(
        lambda row: pd.Series(
            mc.to_hex(scale_lightness((row["r"], row["g"], row["b"]), 0.5))
        ),
        axis=1,
    )
    grid.sort_values(["y", "x"], ascending=[False, True], inplace=True)
    grid = grid.to_crs(epsg=4326)
    grid_list = [[point.xy[1][0], point.xy[0][0]] for point in grid.geometry]
    elevation = grid["elevation_quant"].values / ELEVATION_FRACTION
    color = grid["color"].values
    color_shadow = grid["color_shadow"].values
    elev_min = 0
    elev_max = grid["elevation"].max()
    # eleation = np.round(10 * ((elevation - elev_min) / elev_max))
    for point, elev, col, col_shd in zip(grid_list, elevation, color, color_shadow):
        if elev < 10:
            elev = 10
        brick_icon = BrickIcon(zoom, elev, col, col_shd)
        anchor_shift = elev
        icon_anchor = (elev * zoom, elev * zoom)
        marker = folium.Marker(
            point,
            icon=folium.DivIcon(
                icon_anchor=icon_anchor,
                html=brick_icon.generate_svg(),
            ),
        )
        feature_group.add_child(marker)

map_meta = st_folium(
    m,
    feature_group_to_add=feature_group,
    use_container_width=True,
    #width=map_width,
    #height=map_height,
)

if (
    st.session_state["bounds"] != map_meta["bounds"]
    or st.session_state["zoom"] != map_meta["zoom"]
):

    st.session_state["bounds"] = map_meta["bounds"]
    st.session_state["zoom"] = map_meta["zoom"]
    st.rerun()
