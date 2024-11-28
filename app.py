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
CENTER_START = [0, 0]
ZOOM_START = 10


if "bounds" not in st.session_state:
    st.session_state["bounds"] = {
        "_southWest": {"lat": -85.06, "lng": -180},
        "_northEast": {"lat": 85.06, "lng": 180},
    }

m = folium.Map(
    location=CENTER_START,
    zoom_start=ZOOM_START,
    min_lat=-85.06,
    max_lat=85.06,
    min_lon=-180,
    max_lon=180,
    max_bounds=True,
    min_zoom=2,
    max_zoom=7,
)
sw = [-85.06, -180]
ne = [85.06, 180]
m.fit_bounds([sw, ne])

feature_group = folium.map.FeatureGroup(name="Points")

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
        layer="brixels_world_128000",
        bbox=tuple(bounds),
    )
    grid = grid.to_crs(epsg=4326)
    grid_list = [[point.xy[1][0], point.xy[0][0]] for point in grid.geometry]
    elevation = grid["elevation_trim"].values
    for point, elev in zip(grid_list, elevation):
        marker = folium.Marker(
            (point[0] + elev / 10000, point[1] - elev / 10000),
            # icon=folium.features.CustomIcon(
            #     icon_image=icon_path, icon_size=[brick_size, brick_size]
            # ),
            # icon=folium.DivIcon(
            #     html=f"""<div><svg height="50" width="50"><path d="m 10 25 a 15 15 0 0 0 30 0 a 15 15 0 0 0 -30 0 z " stroke="black"  fill="white" /></svg></div>"""
            # ),
            icon=folium.DivIcon(
                html=f"""<div><svg
   width="25px"
   height="25px"
   viewBox="0 0 50 50"
   version="1.1"
   id="svg1"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg">
  <defs
     id="defs1" />
  <g
     id="layer1">
    <rect
       style="fill:#ff0000;fill-opacity:1;stroke:#800000;stroke-width:1;stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
       id="square"
       width="49"
       height="49"
       x="0.5"
       y="0.5" />
    <circle
       style="fill:#800000;fill-opacity:1;stroke:#800000;stroke-width:1;stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
       id="circle_base"
       cx="25"
       cy="25"
       r="14.5" />
    <path
       style="fill:#ff0000;fill-opacity:1;stroke:#800000;stroke-width:30;stroke-linecap:butt;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
       d="M 25,25 20,20"
       id="circle_height" />
    <circle
       style="fill:#ff0000;fill-opacity:1;stroke:#800000;stroke-width:1;stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
       id="circle_top"
       cx="20"
       cy="20"
       r="14.5" />
  </g>
</svg>
</div>"""
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
    st.rerun()
np.sqrt(50)
