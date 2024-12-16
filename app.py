import colorsys
import os

import folium
import geopandas as gpd
import matplotlib.colors as mc
import numpy as np
import pandas as pd
import streamlit as st
from pyproj import CRS
from shapely import box
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval

os.chdir(os.path.dirname(__file__))
from cmaptools import joincmap, readcpt

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
    9: 8000,
    10: 8000,
    11: 8000,
}

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
max_zoom = 11
CENTER_START = [0, 0]
ZOOM_START = 1
ELEVATION_FRACTION = 12800

cmap_neg = readcpt("cpt/gmt/nighttime_low.cpt")
cmap_pos = readcpt("cpt/gmt/nighttime_high.cpt")
cmap_combined = joincmap(cmap_neg, cmap_pos)

if "bounds" not in st.session_state:
    st.session_state["bounds"] = {
        "_southWest": {"lat": -85.06, "lng": -180},
        "_northEast": {"lat": 85.06, "lng": 180},
    }
if "zoom" not in st.session_state:
    st.session_state["zoom"] = ZOOM_START


def traverse(d):
    for key, val in d.items():
        if isinstance(val, dict):
            yield from traverse(val)
        else:
            yield val


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


def scale_lightness(rgb, scale):
    # convert rgb to hls
    h, l, s = colorsys.rgb_to_hls(*rgb)
    # manipulate h, l, s values and return as rgb
    return colorsys.hls_to_rgb(h, min(1, l * scale), s=min(1, s * scale**2))


def calculate_zoom_divisor(grid_size: int) -> float:
    """Calculate the zoom divisor based on grid size
    Reference:  512000m -> 15
                256000m -> 30
                128000m -> 60
    Formula: divisor = 30 * (256000/grid_size)
    """
    return 15 * (512000 / grid_size)


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

feature_group = folium.map.FeatureGroup(name="Points")

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

    norm = mc.TwoSlopeNorm(vmin=-8000, vcenter=0, vmax=8000)
    # Apply the combined colormap to elevation data
    grid[["r", "g", "b", "a"]] = grid["elevation"].apply(
        lambda x: pd.Series(cmap_combined(norm(x)))
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
    elevation = grid["elevation"].values
    elev_min = 0
    elev_max = np.max(elevation)
    elevation = 10 * np.round(10 * ((elevation - elev_min) / elev_max))
    color = grid["color"].values
    color_shadow = grid["color_shadow"].values

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
    # width=map_width,
    # height=map_height,
)

if (
    st.session_state["bounds"] != map_meta["bounds"]
    or st.session_state["zoom"] != map_meta["zoom"]
):

    st.session_state["bounds"] = map_meta["bounds"]
    st.session_state["zoom"] = map_meta["zoom"]
    st.rerun()
