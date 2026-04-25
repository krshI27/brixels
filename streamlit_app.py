import colorsys
from functools import lru_cache

import folium
import geopandas as gpd
import matplotlib.colors as mc
import numpy as np
import pandas as pd
import streamlit as st
from cmaptools import joincmap, readcpt
from pyproj import CRS
from shapely import box
from src.r2_storage import load_grid_data_r2
from streamlit_folium import st_folium

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


st.session_state["grid_size_dict"] = {
    1: 512000,
    2: 512000,
    3: 512000,
    4: 256000,
    5: 128000,
    6: 64000,
    7: 32000,
    8: 16000,
    9: 8000,
    10: 8000,
}


map_width = 900
map_height = 600

min_zoom = 1
max_zoom = 10
CENTER_START = [20, 15]
ZOOM_START = 2
ELEVATION_FRACTION = 12800

# Curated colormaps suited for elevation (symmetric / diverging around sea level)
COLORMAPS = {
    "Geo": "cpt/gmt/geo.cpt",
    "Globe": "cpt/gmt/globe.cpt",
    "Etopo": "cpt/gmt/etopo1.cpt",
    "Relief": "cpt/gmt/relief.cpt",
    "Terra": "cpt/gmt/terra.cpt",
    "Oleron": "cpt/SCM/oleron.cpt",
    "Vik": "cpt/SCM/vik.cpt",
    "Roma": "cpt/SCM/roma.cpt",
}

BASEMAPS = {
    "Color": "https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}.png",
    "Greyscale": "CartoDB positron",
    "None": None,
}


def cmap_to_css_gradient(cmap, n_stops=12):
    """Generate a CSS linear-gradient string from a matplotlib colormap."""
    norm = mc.TwoSlopeNorm(vmin=-8000, vcenter=0, vmax=8000)
    values = np.linspace(-8000, 8000, n_stops)
    colors = [mc.to_hex(cmap(norm(v))[:3]) for v in values]
    stops = ", ".join(colors)
    return f"linear-gradient(to right, {stops})"


@st.cache_data
def build_cmap_previews():
    """Precompute gradient CSS for each colormap."""
    previews = {}
    for name, path in COLORMAPS.items():
        cmap = readcpt(path)
        previews[name] = cmap_to_css_gradient(cmap)
    return previews


cmap_previews = build_cmap_previews()

def build_brick_info_svg(grid_km, elev_per_plate):
    """Build an SVG diagram of a 1x1 brick (3 plates) with LEGO-accurate proportions.

    LEGO units: 1p = 1.6mm. Plate = 2p high, Brick = 6p high (3 plates),
    Stud = 3p wide × 1p tall, 1x1 pitch = 5p wide.
    """
    # Scale: 1 LEGO unit (1p = 1.6mm) = 10px
    p = 10  # px per LEGO unit
    plate_h = 2 * p    # 20px (3.2mm)
    brick_h = 6 * p    # 60px (9.6mm = 3 plates)
    body_w = 5 * p      # 50px (8.0mm pitch)
    stud_w = 3 * p      # 30px (4.8mm)
    stud_h = 1 * p      # 10px (1.6mm)
    # Layout offsets (room for labels)
    bx, by = 70, 12  # top-left of brick body (below stud)
    w, h = 260, 120

    col = "#FF9A72"
    col_dark = "#d0765a"
    col_line = "#666"
    fs = 'style="font-family:monospace;font-size:10px;fill:#333"'
    fs_sm = 'style="font-family:monospace;font-size:9px;fill:#555"'

    elev_per_brick = elev_per_plate * 3

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'

    # Brick body (single rect for the full height)
    body_top = by + stud_h
    svg += f'<rect x="{bx}" y="{body_top}" width="{body_w}" height="{brick_h}" fill="{col}" stroke="{col_dark}" stroke-width="1.5" rx="1"/>'

    # Plate divider lines (dashed)
    for i in range(1, 3):
        ly = body_top + i * plate_h
        svg += f'<line x1="{bx+1}" y1="{ly}" x2="{bx+body_w-1}" y2="{ly}" stroke="{col_dark}" stroke-width="0.8" stroke-dasharray="3,2"/>'

    # Stud on top (centered)
    stud_x = bx + (body_w - stud_w) / 2
    svg += f'<rect x="{stud_x}" y="{by}" width="{stud_w}" height="{stud_h}" fill="{col}" stroke="{col_dark}" stroke-width="1.5" rx="1"/>'

    # Right side: plate height labels with tick marks
    rx = bx + body_w + 5  # right edge + gap
    for i in range(3):
        pt = body_top + i * plate_h
        pb = pt + plate_h
        mid = (pt + pb) / 2 + 3
        # Tick marks
        svg += f'<line x1="{rx}" y1="{pt}" x2="{rx+8}" y2="{pt}" stroke="{col_line}" stroke-width="0.7"/>'
        svg += f'<line x1="{rx}" y1="{pb}" x2="{rx+8}" y2="{pb}" stroke="{col_line}" stroke-width="0.7"/>'
        svg += f'<line x1="{rx+4}" y1="{pt}" x2="{rx+4}" y2="{pb}" stroke="{col_line}" stroke-width="0.7"/>'
        # Label: "1p = Xm"
        svg += f'<text x="{rx+12}" y="{mid}" {fs_sm}>1p={elev_per_plate:.0f}m</text>'

    # Left side: brick height bracket with label
    lx = bx - 6
    bt = body_top
    bb = body_top + brick_h
    svg += f'<line x1="{lx}" y1="{bt}" x2="{lx}" y2="{bb}" stroke="{col_line}" stroke-width="0.8"/>'
    svg += f'<line x1="{lx-4}" y1="{bt}" x2="{lx+3}" y2="{bt}" stroke="{col_line}" stroke-width="0.8"/>'
    svg += f'<line x1="{lx-4}" y1="{bb}" x2="{lx+3}" y2="{bb}" stroke="{col_line}" stroke-width="0.8"/>'
    mid_y = (bt + bb) / 2
    svg += f'<text x="{lx-6}" y="{mid_y-2}" text-anchor="end" {fs}>1b</text>'
    svg += f'<text x="{lx-6}" y="{mid_y+10}" text-anchor="end" {fs_sm}>{elev_per_brick:.0f}m</text>'

    # Bottom: grid size dimension line
    bot_y = body_top + brick_h + 10
    svg += f'<line x1="{bx}" y1="{bot_y}" x2="{bx+body_w}" y2="{bot_y}" stroke="{col_line}" stroke-width="0.8"/>'
    svg += f'<line x1="{bx}" y1="{bot_y-3}" x2="{bx}" y2="{bot_y+3}" stroke="{col_line}" stroke-width="0.8"/>'
    svg += f'<line x1="{bx+body_w}" y1="{bot_y-3}" x2="{bx+body_w}" y2="{bot_y+3}" stroke="{col_line}" stroke-width="0.8"/>'
    svg += f'<text x="{bx+body_w/2}" y="{bot_y+13}" text-anchor="middle" {fs}>{grid_km:.0f} km</text>'

    svg += '</svg>'
    return svg


with st.sidebar:
    # Title at the top of sidebar
    st.markdown(
        '<h1 style="margin:0;padding:0;line-height:1;">Brixels</h1>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    cmap_names = list(COLORMAPS.keys())
    # Initialize user preferences in session state
    if "cmap_selection" not in st.session_state:
        st.session_state["cmap_selection"] = cmap_names[0]
    if "basemap_selection" not in st.session_state:
        st.session_state["basemap_selection"] = "Color"
    if "show_water" not in st.session_state:
        st.session_state["show_water"] = True
    if "show_land" not in st.session_state:
        st.session_state["show_land"] = True

    cmap_name = st.session_state["cmap_selection"]
    cmap_path = COLORMAPS[cmap_name]

    # Show selected gradient preview, expander for full list
    sel_grad = cmap_previews[cmap_name]
    st.markdown("### Colormap")
    st.markdown(
        f'<div style="height:18px;border-radius:4px;background:{sel_grad};'
        f'border:2px solid #FF9A72;margin-bottom:4px;"></div>',
        unsafe_allow_html=True,
    )
    with st.expander("Change colormap"):
        for name in cmap_names:
            grad = cmap_previews[name]
            is_selected = cmap_name == name
            border = "2px solid #FF9A72" if is_selected else "2px solid transparent"
            opacity = "1" if is_selected else "0.7"
            st.markdown(
                f'<div title="{name}" style="height:14px;border-radius:3px;background:{grad};'
                f'border:{border};margin-bottom:4px;opacity:{opacity};cursor:pointer;"></div>',
                unsafe_allow_html=True,
            )
            if st.button(name, key=f"cmap_{name}", use_container_width=True):
                st.session_state["cmap_selection"] = name
                st.rerun()

    st.markdown("### Basemap")
    basemap_names = list(BASEMAPS.keys())
    basemap_index = basemap_names.index(st.session_state["basemap_selection"])
    basemap_name = st.selectbox(
        "Basemap",
        basemap_names,
        index=basemap_index,
        label_visibility="collapsed",
        key="basemap_selector",
        on_change=lambda: st.session_state.update({"basemap_selection": st.session_state["basemap_selector"]}),
    )

    st.markdown("### Display")
    show_water = st.toggle("Show Water", value=True, key="show_water")
    show_land = st.toggle("Show Land", value=True, key="show_land")

    # Reset View button
    if st.button("🔄 Reset View", use_container_width=True, key="reset_view"):
        st.session_state["bounds"] = {
            "_southWest": {"lat": -85.06, "lng": -180},
            "_northEast": {"lat": 85.06, "lng": 180},
        }
        st.session_state["zoom"] = ZOOM_START
        st.rerun()

    # Export Map button
    st.button("📥 Export Map", use_container_width=True, key="export_map", help="Download current map view as PNG")

    st.markdown("---")
    st.markdown("### Map Info")
    z = st.session_state.get("zoom", ZOOM_START)
    gs = st.session_state["grid_size_dict"].get(z, 0)
    elev_max_view = st.session_state.get("elev_max", 8000)
    elev_per_plate = elev_max_view / 10  # 10 plates = max quantized height
    brick_svg = build_brick_info_svg(gs / 1000, elev_per_plate)
    st.markdown(brick_svg, unsafe_allow_html=True)

cmap_combined = readcpt(cmap_path)
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


def zoom_decimals(zoom):
    """Rounding precision (decimal places) appropriate for each zoom level."""
    return zoom // 3


def snap_bounds(bounds, zoom):
    """Snap bounds outward with padding so bricks extend past all viewport edges."""
    decimals = zoom_decimals(zoom)
    step = 10**-decimals
    # Pad by one grid cell so brick bases from beyond the edge fill into view
    grid_size = st.session_state["grid_size_dict"][zoom]
    pad = 2 * grid_size / 111320  # ~2 grid cells in degrees (extra for Mercator distortion)
    return {
        "_southWest": {
            "lat": max(-85.06, np.floor((bounds["_southWest"]["lat"] - pad) / step) * step),
            "lng": max(-180, np.floor((bounds["_southWest"]["lng"] - pad) / step) * step),
        },
        "_northEast": {
            "lat": min(85.06, np.ceil((bounds["_northEast"]["lat"] + pad) / step) * step),
            "lng": min(180, np.ceil((bounds["_northEast"]["lng"] + pad) / step) * step),
        },
    }


@st.cache_data
def load_grid_data(layer_name, bounds, columns):
    """Cache grid data loading - uses R2 or local file"""
    return load_grid_data_r2(layer_name, tuple(bounds), columns)


@lru_cache(maxsize=256)
def generate_brick_svg(zoom, elevation, color, color_shadow):
    """Cache SVG generation for repeated combinations"""
    brick = BrickIcon(zoom, elevation, color, color_shadow)
    return brick.generate_svg()


class BrickIcon:
    def __init__(self, zoom, elevation, color="#277AA2", color_shadow="#08567C"):
        self.zoom = float(zoom)  # Ensure float for faster calculations
        self.elevation = float(elevation)
        self.color = color
        self.color_shadow = color_shadow
        # Pre-calculate common values
        self._zoom_49 = self.zoom * 49
        self._zoom_25 = self.zoom * 25
        self._zoom_05 = self.zoom * 0.5

    def _create_square_base(self):
        return f"""<rect
            style="fill:{self.color_shadow};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            id="square_base"
            width="{self._zoom_49}"
            height="{self._zoom_49}"
            x="{self.zoom*(self.elevation+0.5)}"
            y="{self.zoom*(self.elevation+0.5)}" />"""

    def _create_square_height(self):
        return f"""<path
            style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{np.sqrt(2*((self.zoom*50)**2))};stroke-linecap:butt;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            d="M {self._zoom_25},{self._zoom_25} {self.zoom*(self.elevation+25)},{self.zoom*(self.elevation+25)}"
            id="square_height" />"""

    def _create_square_top(self):
        return f"""<rect
            style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            id="square_top"
            width="{self._zoom_49}"
            height="{self._zoom_49}"
            x="{self._zoom_05}"
            y="{self._zoom_05}" />"""

    def _create_circle_base(self):
        return f"""<circle
            style="fill:{self.color_shadow};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*1};stroke-linecap:square;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            id="circle_base"
            cx="{self._zoom_25}"
            cy="{self._zoom_25}"
            r="{self.zoom*14.5}" />"""

    def _create_circle_height(self):
        return f"""<path
            style="fill:{self.color};fill-opacity:1;stroke:{self.color_shadow};stroke-width:{self.zoom*30};stroke-linecap:butt;stroke-dasharray:none;stroke-opacity:1;paint-order:normal"
            d="M {self.zoom*20},{self.zoom*20} {self._zoom_25},{self._zoom_25}"
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


def process_colors(values, norm=None):
    """Vectorized color processing"""
    if norm is None:
        norm = mc.TwoSlopeNorm(vmin=-8000, vcenter=0, vmax=8000)
    colors = np.array([cmap_combined(norm(v)) for v in values])

    # Vectorized color calculations
    hex_colors = np.apply_along_axis(lambda x: mc.to_hex(x[:3]), 1, colors)
    shadow_colors = np.apply_along_axis(
        lambda x: mc.to_hex(scale_lightness(x[:3], 0.5)), 1, colors
    )
    return hex_colors, shadow_colors


@st.fragment
def main():
    # Restore map position from session state (prevents reset on fragment rerun)
    bounds_state = st.session_state["bounds"]
    sw = bounds_state["_southWest"]
    ne = bounds_state["_northEast"]
    center = [(sw["lat"] + ne["lat"]) / 2, (sw["lng"] + ne["lng"]) / 2]
    current_zoom = st.session_state["zoom"]

    basemap_tile = BASEMAPS[basemap_name]

    # Handle different basemap types
    if basemap_tile is None:
        # No basemap - use a white/transparent base
        m = folium.Map(
            location=center,
            zoom_start=current_zoom,
            min_lat=-85.06,
            max_lat=85.06,
            min_lon=-180,
            max_lon=180,
            max_bounds=True,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            tiles=None,
            prefer_canvas=True,
        )
        # Add a simple white background CSS
        m.get_root().html.add_child(folium.Element(
            '<style>.leaflet-container { background: white !important; }</style>'
        ))
    elif isinstance(basemap_tile, str) and basemap_tile.startswith("http"):
        # Custom URL template
        m = folium.Map(
            location=center,
            zoom_start=current_zoom,
            min_lat=-85.06,
            max_lat=85.06,
            min_lon=-180,
            max_lon=180,
            max_bounds=True,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            tiles=None,
            prefer_canvas=True,
        )
        folium.TileLayer(
            tiles=basemap_tile,
            attr="Stadia/Stamen",
            name="Stamen Terrain",
        ).add_to(m)
    else:
        # Named tileset
        m = folium.Map(
            location=center,
            zoom_start=current_zoom,
            min_lat=-85.06,
            max_lat=85.06,
            min_lon=-180,
            max_lon=180,
            max_bounds=True,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            tiles=basemap_tile,
            prefer_canvas=True,
        )

    feature_group = folium.map.FeatureGroup(name="Points")

    if not any(pd.isna([val for val in traverse(st.session_state["bounds"])])):
        grid_size = st.session_state["grid_size_dict"][current_zoom]
        y_min, x_min, y_max, x_max = traverse(st.session_state["bounds"])
        x_min = max(-180, x_min)
        x_max = min(180, x_max)

        # Create bounding box and transform coordinates
        bounding_box = box(x_min, y_min, x_max, y_max)
        gdf = gpd.GeoDataFrame(geometry=[bounding_box], crs=CRS.from_epsg(4326))
        bounds = gdf.to_crs(epsg=3857).total_bounds

        layer_name = f"brixels_world_{grid_size:06d}"
        grid = load_grid_data(layer_name, bounds, ["elevation", "geometry"])

        # Water/land filtering
        if not show_water:
            grid = grid[grid["elevation"] > 0]
        if not show_land:
            grid = grid[grid["elevation"] <= 0]

        if len(grid) > 0:
            grid["x"] = grid.geometry.x
            grid["y"] = grid.geometry.y

            zoom_divisor = calculate_zoom_divisor(grid_size)
            zoom = (2 ** current_zoom) / zoom_divisor

            grid.sort_values(["y", "x"], ascending=[False, True], inplace=True)
            grid = grid.to_crs(epsg=4326)

            grid_list = np.column_stack((grid.geometry.y, grid.geometry.x)).tolist()

            raw_elevation = grid["elevation"].values
            elev_max = np.max(np.abs(raw_elevation))
            st.session_state["elev_max"] = float(elev_max)

            colors, shadow_colors = process_colors(raw_elevation)

            if elev_max > 0:
                elevation = np.maximum(
                    10 * np.round(10 * (raw_elevation / elev_max)), 10
                )
            else:
                elevation = np.full_like(raw_elevation, 10)

            feature_group = folium.map.FeatureGroup(name="Points")
            for point, elev, raw_elev, col, col_shd in zip(
                grid_list, elevation, raw_elevation, colors, shadow_colors
            ):
                svg = generate_brick_svg(zoom, elev, col, col_shd)
                icon_anchor = (elev * zoom, elev * zoom)
                # Compact brick/plate notation (e.g., "3200m | 3b2p")
                n_plates = int(elev / 10)
                n_bricks = n_plates // 3
                remainder = n_plates % 3
                parts = ""
                if n_bricks > 0:
                    parts += f"{n_bricks}b"
                if remainder > 0 or n_bricks == 0:
                    parts += f"{remainder}p"
                tip = f"{int(raw_elev)}m | {parts}"
                marker = folium.Marker(
                    point,
                    icon=folium.DivIcon(
                        icon_anchor=icon_anchor,
                        html=svg,
                    ),
                    tooltip=tip,
                )
                feature_group.add_child(marker)

    map_meta = st_folium(
        m,
        feature_group_to_add=feature_group,
        use_container_width=True,
        height=800,
    )

    # Update state when bounds or zoom change
    if map_meta and "bounds" in map_meta and "zoom" in map_meta:
        bounds_values = [val for val in traverse(map_meta["bounds"])]
        if not any(pd.isna(bounds_values)):
            new_zoom = int(round(map_meta["zoom"]))
            new_bounds = snap_bounds(map_meta["bounds"], new_zoom)

            state_changed = (
                new_bounds != st.session_state["bounds"]
                or new_zoom != st.session_state["zoom"]
            )

            if state_changed and min_zoom <= new_zoom <= max_zoom:
                if st.session_state.get("_rerun_pending"):
                    # First return after a rerun — absorb render jitter, don't loop
                    st.session_state["_rerun_pending"] = False
                else:
                    zoom_changed = new_zoom != st.session_state["zoom"]
                    st.session_state["bounds"] = new_bounds
                    st.session_state["zoom"] = new_zoom
                    st.session_state["_rerun_pending"] = True
                    if zoom_changed:
                        # Full rerun so sidebar (Map Info) updates
                        st.rerun()
                    else:
                        st.rerun(scope="fragment")
            else:
                st.session_state["_rerun_pending"] = False


if __name__ == "__main__":
    main()

    # Add export functionality via JavaScript
    if st.session_state.get("export_map", False):
        st.markdown("""
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
        <script>
        // Export map functionality
        function exportMap() {
            const mapElement = document.querySelector('iframe').contentWindow.document.querySelector('.leaflet-container');
            if (mapElement) {
                html2canvas(mapElement, {
                    useCORS: true,
                    allowTaint: true,
                    backgroundColor: '#e8e8e8',
                    scale: 2
                }).then(canvas => {
                    const link = document.createElement('a');
                    const timestamp = new Date().toISOString().slice(0,19).replace(/:/g,'-');
                    link.download = `brixels-map-${timestamp}.png`;
                    link.href = canvas.toDataURL('image/png');
                    link.click();
                });
            }
        }

        // Auto-trigger export when button is clicked
        setTimeout(exportMap, 500);
        </script>
        """, unsafe_allow_html=True)
