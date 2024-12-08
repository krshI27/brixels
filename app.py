import json
import os
import random
import time
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


def elevation_request(url: str, location: str) -> json:
    """
    Makes the remote request
    Continues making attempts until it succeeds
    """

    count = 1
    while True:
        try:
            response = urlopen(url + location).read().decode("utf-8")
        except (OSError, urllib3.exceptions.ProtocolError) as error:
            print("\n")
            print("*" * 20, "Error Occured", "*" * 20)
            print(f"Number of tries: {count}")
            print(f"URL: {url}")
            print(error)
            print("\n")
            count += 1
            time.sleep(5)
            continue
        break

    return response


def get_elevation(x):
    elevations = []
    url = "https://api.open-elevation.com/api/v1/lookup?locations="
    for lat, lon in x:
        location = f"{lat},{lon}"
        response = elevation_request(url, location)
        response = json.loads(response)
        elevations.append(response["results"][0]["elevation"])
    return elevations


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


icon_path = "static/brick_top.png"

brick_size = 10
map_width = 1000
map_height = 500
min_zoom = 2
CENTER_START = [0, 0]
ZOOM_START = 5


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
    max_zoom=7,
)
sw = [-85.06, -180]
ne = [85.06, 180]
m.fit_bounds([sw, ne])

feature_group = folium.map.FeatureGroup(name="Points")

class BrickIcon:
    def __init__(self, zoom, elevation, color, color_shadow):
        self.zoom = zoom
        self.elevation = elevation
        self.color = color
        self.color_shadow = color_shadow
        self.size = 55 + elevation

    def _create_base_square(self):
        return f"""<rect
           style="fill:{self.color_shadow};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
           id="square"
           width="{self.zoom*49}"
           height="{self.zoom*49}"
           x="{self.zoom*(5.5+self.elevation)}"
           y="{self.zoom*(5.5+self.elevation)}" />"""

    def _create_square_height(self):
        return f"""<path
           style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{np.sqrt(2*((self.zoom*50)**2))};stroke-linecap:butt;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
           d="M {self.zoom*25},{self.zoom*25} {self.zoom*(30+self.elevation)},{self.zoom*(30+self.elevation)}"
           id="circle_height" />"""

    def _create_top_square(self):
        return f"""<rect
           style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
           id="square"
           width="{self.zoom*49}"
           height="{self.zoom*49}"
           x="{self.zoom*0.5}"
           y="{self.zoom*0.5}" />"""

    def _create_base_circle(self):
        return f"""<circle
           style="fill:{self.color_shadow};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
           id="circle_base"
           cx="{self.zoom*25}"
           cy="{self.zoom*25}"
           r="{self.zoom*14.5}" />"""

    def _create_circle_height(self):
        return f"""<path
           style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*30};stroke-linecap:butt;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
           d="M {self.zoom*25},{self.zoom*25} {self.zoom*20},{self.zoom*20}"
           id="circle_height" />"""

    def _create_top_circle(self):
        return f"""<circle
           style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
           id="circle_top"
           cx="{self.zoom*20}"
           cy="{self.zoom*20}"
           r="{self.zoom*14.5}" />"""

    def generate_svg(self):
        return f"""<div><svg
       width="{self.zoom*self.size}px"
       height="{self.zoom*self.size}px"
       viewBox="0 0 {self.zoom*self.size} {self.zoom*self.size}"
       version="1.1"
       id="svg1"
       xmlns="http://www.w3.org/2000/svg"
       xmlns:svg="http://www.w3.org/2000/svg">
      <defs id="defs1" />
      <g id="layer1">
        {self._create_base_square()}
        {self._create_square_height()}
        {self._create_top_square()}
        {self._create_base_circle()}
        {self._create_circle_height()}
        {self._create_top_circle()}
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

if not any(pd.isna([val for val in traverse(st.session_state["bounds"])])):
    y_min, x_min, y_max, x_max = traverse(st.session_state["bounds"])
    bounding_box = box(x_min, y_min, x_max, y_max)
    gdf = gpd.GeoDataFrame(geometry=[bounding_box], crs=CRS.from_epsg(4326))
    gdf = gdf.to_crs(epsg=3857)
    bounds = gdf.total_bounds
    # grid = create_grid(bounds, brick_size, map_width, map_height)
    # grid = gpd.GeoDataFrame(
    #     geometry=[Point(x, y) for x, y in grid], crs=CRS.from_epsg(3857)
    # )
    grid = gpd.read_file(
        "/data/brixels_world_512000-008000.gpkg",
        layer="brixels_world_256000",
        bbox=tuple(bounds),
    )
    grid["x"] = grid.geometry.x
    grid["y"] = grid.geometry.y
    
    # Replace the separate color calculations with ColorUtils
    grid[["color", "color_shadow"]] = (
        grid["elevation"]
        .apply(lambda x: pd.Series(ColorUtils.create_color_pair(x, base_range=(grid["elevation"].min(), grid["elevation"].max()))))
    )
    
    grid.sort_values(["y", "x"], ascending=[False, True], inplace=True)
    grid = grid.to_crs(epsg=4326)
    grid_list = [[point.xy[1][0], point.xy[0][0]] for point in grid.geometry]
    elevation = grid["elevation_trim"].values
    color = grid["color"].values
    color_shadow = grid["color_shadow"].values
    zoom = (2 ** st.session_state["zoom"]) / 30
    for point, elev, col, col_shd in zip(grid_list, elevation, color, color_shadow):
        elev /= 200
        brick_icon = BrickIcon(zoom, elev, col, col_shd)
        marker = folium.Marker(
            point,
            icon=folium.DivIcon(
                icon_anchor=(elev * zoom, elev * zoom),
                html=brick_icon.generate_svg(),
            ),
        )
        feature_group.add_child(marker)

map_meta = st_folium(
    m,
    feature_group_to_add=feature_group,
    width=map_width,
    height=map_height,
)

if st.session_state["bounds"] != map_meta["bounds"]:

    st.session_state["bounds"] = map_meta["bounds"]
    st.session_state["zoom"] = map_meta["zoom"]
    st.rerun()
np.sqrt(50)
