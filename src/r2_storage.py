"""
Cloudflare R2 storage integration for Brixels.

Provides tile-based data loading from R2 with local file fallback for development.
Uses GeoParquet tiles partitioned by geographic region for efficient loading.
"""

import json
import os
from io import BytesIO
from pathlib import Path

import boto3
import geopandas as gpd
import pandas as pd
import streamlit as st
from botocore.config import Config

# ============================================================================
# R2 Client Setup
# ============================================================================


def get_r2_client():
    """Create R2 client using Streamlit secrets."""
    endpoint = (
        st.secrets.get("CLOUDFLARE_S3_API")
        or f"https://{st.secrets.get('CLOUDFLARRE_ACCOUNT_ID', st.secrets.get('R2_ACCOUNT_ID'))}.r2.cloudflarestorage.com"
    )
    access_key = st.secrets.get("R2_ACCESS_ID") or st.secrets.get("R2_ACCESS_KEY")
    secret_key = st.secrets.get("R2_SECRET_ACCESS_KEY") or st.secrets.get(
        "R2_SECRET_KEY"
    )

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"}),
    )


# ============================================================================
# Local Development Detection
# ============================================================================


def is_local_dev() -> bool:
    """Check if running in local development mode with local data."""
    local_gpkg = Path("/data/brixels_world_512000-008000.gpkg")
    local_parquet = Path(
        "/Users/maximiliansperlich/Developer/projects/data/brixels_parquet/index.json"
    )
    return local_gpkg.exists() or local_parquet.exists()


def get_local_parquet_dir() -> Path | None:
    """Get local parquet directory if available."""
    local_dir = Path(
        "/Users/maximiliansperlich/Developer/projects/data/brixels_parquet"
    )
    if local_dir.exists():
        return local_dir
    return None


# ============================================================================
# Tile Index Management
# ============================================================================


@st.cache_resource
def load_tile_index() -> dict:
    """Load the tile index from local storage or R2."""
    local_dir = get_local_parquet_dir()

    if local_dir:
        index_path = local_dir / "index.json"
        if index_path.exists():
            with open(index_path) as f:
                return json.load(f)

    # Load from R2
    r2 = get_r2_client()
    bucket = st.secrets.get("R2_BUCKET_NAME", "brixels-data")

    response = r2.get_object(Bucket=bucket, Key="parquet/index.json")
    return json.loads(response["Body"].read().decode("utf-8"))


def get_tiles_for_bounds(bounds: tuple, grid_size: str) -> list[dict]:
    """
    Get list of tiles that intersect with the given bounds.

    Args:
        bounds: (minx, miny, maxx, maxy) in EPSG:3857
        grid_size: Grid size string (e.g., "512000")

    Returns:
        List of tile metadata dicts
    """
    index = load_tile_index()
    tile_size = index["tile_size_degrees"]

    minx, miny, maxx, maxy = bounds

    # Convert bounds from EPSG:3857 to EPSG:4326 (approximate)
    # For more accuracy, use pyproj transform
    lon_min = max(-180, minx / 111320)
    lon_max = min(180, maxx / 111320)
    lat_min = max(-90, miny / 110540)
    lat_max = min(90, maxy / 110540)

    # Find intersecting tiles
    matching_tiles = []
    for tile in index["tiles"]:
        if tile["grid_size"] != grid_size:
            continue

        # Check intersection
        if (
            tile["max_x"] > lon_min
            and tile["min_x"] < lon_max
            and tile["max_y"] > lat_min
            and tile["min_y"] < lat_max
        ):
            matching_tiles.append(tile)

    return matching_tiles


# ============================================================================
# Tile Loading
# ============================================================================


@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_tile(tile_file: str) -> gpd.GeoDataFrame:
    """
    Load a single tile from local storage or R2.

    Args:
        tile_file: Relative path to tile file (e.g., "512000/tile_-180_-90.parquet")

    Returns:
        GeoDataFrame with tile data
    """
    local_dir = get_local_parquet_dir()

    if local_dir:
        tile_path = local_dir / tile_file
        if tile_path.exists():
            return gpd.read_parquet(tile_path)

    # Load from R2
    r2 = get_r2_client()
    bucket = st.secrets.get("R2_BUCKET_NAME", "brixels-data")

    response = r2.get_object(Bucket=bucket, Key=f"parquet/{tile_file}")
    data = BytesIO(response["Body"].read())
    return gpd.read_parquet(data)


def load_grid_data_r2(
    layer_name: str, bounds: tuple, columns: list
) -> gpd.GeoDataFrame:
    """
    Load grid data for the given bounds using tiled GeoParquet.

    Args:
        layer_name: Layer name (e.g., "brixels_world_512000")
        bounds: Bounding box tuple (minx, miny, maxx, maxy) in EPSG:3857
        columns: List of columns to load

    Returns:
        GeoDataFrame with requested data
    """
    # Extract grid size from layer name
    grid_size = layer_name.split("_")[-1]

    # Check if we should use legacy GeoPackage (for backwards compatibility)
    local_gpkg = Path("/data/brixels_world_512000-008000.gpkg")
    if local_gpkg.exists() and not get_local_parquet_dir():
        return gpd.read_file(
            str(local_gpkg),
            layer=layer_name,
            bbox=bounds,
            columns=columns,
            engine="pyogrio",
        )

    # Get tiles that intersect the bounds
    tiles = get_tiles_for_bounds(bounds, grid_size)

    if not tiles:
        # Return empty GeoDataFrame with expected columns
        return gpd.GeoDataFrame(columns=columns + ["geometry"])

    # Load and concatenate tiles
    gdfs = []
    for tile in tiles:
        try:
            gdf = load_tile(tile["file"])
            gdfs.append(gdf)
        except Exception as e:
            st.warning(f"Failed to load tile {tile['file']}: {e}")

    if not gdfs:
        return gpd.GeoDataFrame(columns=columns + ["geometry"])

    # Concatenate all tiles
    combined = pd.concat(gdfs, ignore_index=True)
    result = gpd.GeoDataFrame(combined, geometry="geometry")

    # Filter to exact bounds
    minx, miny, maxx, maxy = bounds
    mask = (
        (result.geometry.x >= minx)
        & (result.geometry.x <= maxx)
        & (result.geometry.y >= miny)
        & (result.geometry.y <= maxy)
    )
    result = result[mask]

    # Select only requested columns
    available_cols = [c for c in columns if c in result.columns]
    return result[available_cols + ["geometry"]]


# ============================================================================
# Legacy Support (deprecated, will be removed)
# ============================================================================


@st.cache_resource
def get_brixels_data_source():
    """
    DEPRECATED: Get the data source path for legacy GeoPackage loading.
    Use load_grid_data_r2() with tile-based loading instead.
    """
    local_path = "/data/brixels_world_512000-008000.gpkg"

    if os.path.exists(local_path):
        return local_path

    # This path should not be used in production - tiles are preferred
    raise RuntimeError(
        "Legacy GeoPackage loading is deprecated. "
        "Please convert to GeoParquet tiles using scripts/convert_to_parquet.py"
    )
