import itertools

import ee
import geemap
import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point

ee.Authenticate()  # 4/1AeanS0bEtHfxpAEagEZylBp2U5g4pw4E0xaTH2SNXZkKIvBCMIDUcHnJaJ4
ee.Initialize()
dem = ee.Image("NASA/NASADEM_HGT/001")

epsg = 3857
lst_grid_spacing = [512000, 256000]
min_x, min_y, max_x, max_y = -10, -10, 10, 10

transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

min_x, min_y = transformer.transform(min_x, min_y)
max_x, max_y = transformer.transform(max_x, max_y)

for grid_spacing in lst_grid_spacing:
    x_lst = range(
        int(min_x) - grid_spacing, int(max_x) + 2 * grid_spacing, grid_spacing
    )
    y_lst = range(
        int(min_y) - grid_spacing, int(max_y) + 2 * grid_spacing, grid_spacing
    )
transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
points = [
    Point(transformer.transform(x, y)) for x, y in itertools.product(x_lst, y_lst)
]
features = [ee.Feature(ee.Geometry.Point([p.x, p.y])) for p in points]
feature_collection = ee.FeatureCollection(features)

sampled_points = dem.sample(region=feature_collection, scale=30, projection="EPSG:4326")

# Convert the sampled points to a GeoDataFrame
sampled_points_gdf = geemap.ee_to_gdf(sampled_points)

# Print or save the sampled points
print(sampled_points_gdf)
