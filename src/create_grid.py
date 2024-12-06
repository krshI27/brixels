import geopandas as gpd
import pandas as pd
import psycopg2
#from tqdm.contrib.itertools import chain
from pathlib import Path
from itertools import islice, chain, product
from tqdm import tqdm
import numpy as np
import pyproj
pyproj.datadir.set_data_dir(r"C:\Users\maxim\miniconda3\envs\average_sunset\Library\share\proj")
from shapely.geometry import Point
import rasterio
import itertools
from pyproj import Proj, Transformer
from osgeo import gdal
from sqlalchemy import create_engine
# %% parameters

path_shp_countries = Path(r"E:\NASADEM\Natural Earth\10m_cultural\ne_10m_admin_0_countries.shp")
path_dem = Path(r"E:\NASADEM\NASADEM.vrt")
path_ocean = Path(r"E:\NASADEM\Natural Earth\10m_physical\ne_10m_ocean.shp")

"""
gdf_ocean = gpd.read_file(path_ocean)
gdf_ocean.to_crs(epsg, inplace=True)
cur.execute(f"DROP TABLE IF EXISTS lizmap.ocean")

conn.commit()

engine = create_engine('postgresql://postgres:postgres@localhost:5444/postgres')

gdf_ocean.to_postgis(
    con=engine,
    schema="lizmap",
    name="ocean"
)
"""

if not path_dem.exists():
    path_dem_folder = Path(r"E:\NASADEM\NASADEM")
    paths_dem_tifs = [str(path) for path in path_dem_folder.glob("*.tif")]
    vrt = gdal.BuildVRT(str(path_dem), paths_dem_tifs)
    vrt = None
    
epsg = 3857
lst_grid_spacing = [512000, 256000, 128000, 64000, 32000, 16000, 8000]
lst_elevation_quant_levels = [2, 4, 8, 16, 32, 64, 128]
table_name = "points"

# %% functions
def doubling(n, start_value=1):
    x = 1
    out_lst = [x]
    for i in range(n):
        x *= 2
        out_lst.append(x)
    return np.array(out_lst) * start_value

def round_grid_spacing(x, grid_spacing):
    out = []
    for i in x:
        if i >= 0:
            out.append(i // grid_spacing * grid_spacing)
        else:
            out.append(-(-i // grid_spacing * grid_spacing))
    return pd.Series(out)

def chunks(iterable, size=10000):
    iterator = iter(iterable)
    for first in iterator:
        yield chain([first], islice(iterator, size - 1))

def zoom_level(x, y, zoom_levels):
    for zoom_level in sorted(zoom_levels, reverse=True):
        if x % zoom_level == 0 and y % zoom_level == 0:
            return zoom_level

#%% main

for grid_spacing, elevation_quant_levels in zip(lst_grid_spacing, lst_elevation_quant_levels):
    print(grid_spacing, elevation_quant_levels)
    
    # grid_spacing = 50000
    # elevation_quant_levels = 5
    
    conn = psycopg2.connect(dbname="postgres", port=5444, user="postgres",
                                password="postgres", host="localhost")
    
    code = "world"
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    
    src = rasterio.open(path_dem)
    min_x, min_y, max_x, max_y = src.bounds
    min_y = -56
    max_y = 60

    min_x, min_y = transformer.transform(min_x, min_y)
    max_x, max_y = transformer.transform(max_x, max_y)
    shp_countries_bounds = pd.DataFrame([[min_x, min_y, max_x, max_y]]) # -20037508.34,-20048966.1,20037508.34,20048966.1
    shp_countries_bounds.columns = ["minx","miny","maxx","maxy"]
    shp_countries_bounds = shp_countries_bounds.apply(round_grid_spacing, args=(grid_spacing,))
    
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    minx, miny, maxx, maxy = shp_countries_bounds.minx, shp_countries_bounds.miny, shp_countries_bounds.maxx, shp_countries_bounds.maxy
    x_lst = range(int(minx)-grid_spacing, int(maxx)+2*grid_spacing, grid_spacing)
    y_lst = range(int(miny)-grid_spacing, int(maxy)+2*grid_spacing, grid_spacing)
    
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS lizmap.{table_name}_{code}_{grid_spacing:06}")
    cur.execute(f"CREATE TABLE lizmap.{table_name}_{code}_{grid_spacing:06} (geom geometry, grid_spacing int, elevation float, elevation_quant int)")
    conn.commit()
    cur.close()
    
    grid = product(x_lst, y_lst)
    len_grid = len(list(product(x_lst, y_lst)))
    
    alt_min = None
    alt_max = None
    
    cur = conn.cursor()
    for chunk in tqdm(chunks(grid, 1000), total=1+len_grid//1000):
        coords_3857 = [coords for coords in chunk]
        coords_4326 = [transformer.transform(x, y) for (x, y) in coords_3857]
        alt = [alt[0] if alt[0] != -32768 else 0 for alt in src.sample(coords_4326)]
        if alt_min is None:
            alt_min = min(alt)
        elif alt_min > min(alt):
            alt_min = min(alt)
        if alt_max is None:
            alt_max = max(alt)
        elif alt_max < max(alt):
            alt_max = max(alt)
        vals = [(x,y,alt) for ((x,y),alt) in zip(coords_3857, alt)]
        values_string = ",".join(f"(ST_SetSRID(ST_MakePoint({x}, {y}), {epsg}), {grid_spacing}, {alt}, 1)" for (x, y, alt) in vals)
        cur.execute(f"INSERT INTO lizmap.{table_name}_{code}_{grid_spacing:06} (geom, grid_spacing, elevation, elevation_quant) VALUES " + values_string)
    conn.commit()
    cur.close()
    src.close()
    
    cur = conn.cursor()
    cur.execute(f"CREATE INDEX {table_name}_{code}_{grid_spacing:06}_geom_idx ON lizmap.{table_name}_{code}_{grid_spacing:06} USING GIST (geom);")
    conn.commit()
    cur.close()

    
    # elevation_quant
    
    alt_range = alt_max - alt_min
    cur = conn.cursor()
    cur.execute(f"""
    update lizmap.{table_name}_{code}_{grid_spacing:06} pw
    set elevation_quant = round(round(2 + {elevation_quant_levels} * ((pw.elevation - {alt_min}) / {alt_range})) * {grid_spacing} * 0.4)
    """)
    conn.commit()
    cur.close()
    
    
    # ocean
    
    cur = conn.cursor()
    cur.execute(f"""
    update lizmap.{table_name}_{code}_{grid_spacing:06} pw
    set elevation_quant = round(pw.grid_spacing * 0.4),
    elevation = -999
    from lizmap.ocean oc
    where ST_Within(pw.geom, oc.geometry);
    """)
    conn.commit()
    cur.close()
    
    conn.close()

