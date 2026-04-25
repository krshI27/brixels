"""
Cloudflare R2 storage integration for Brixels.

Provides tile-based data loading from R2 with local file fallback for development.
Uses GeoParquet tiles partitioned by geographic region in EPSG:3857.
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
        or f"https://{st.secrets.get('CLOUDFLARE_ACCOUNT_ID', st.secrets.get('R2_ACCOUNT_ID'))}.r2.cloudflarestorage.com"
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
# Local Development Fallback
# ============================================================================

LOCAL_PARQUET_DIR = Path(
    os.environ.get(
        "BRIXELS_PARQUET_DIR",
        "/tmp/brixels_parquet_v2",
    )
)


def get_local_parquet_dir() -> Path | None:
    """Get local parquet directory if available."""
    if LOCAL_PARQUET_DIR.exists() and (LOCAL_PARQUET_DIR / "index.json").exists():
        return LOCAL_PARQUET_DIR
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

    Both bounds and tile boundaries are in EPSG:3857 (meters).

    Args:
        bounds: (minx, miny, maxx, maxy) in EPSG:3857
        grid_size: Grid size string (e.g., "512000")

    Returns:
        List of tile metadata dicts
    """
    index = load_tile_index()
    minx, miny, maxx, maxy = bounds

    matching_tiles = []
    for tile in index["tiles"]:
        if tile["grid_size"] != grid_size:
            continue

        # Direct EPSG:3857 bbox intersection test
        if (
            tile["max_x"] > minx
            and tile["min_x"] < maxx
            and tile["max_y"] > miny
            and tile["min_y"] < maxy
        ):
            matching_tiles.append(tile)

    return matching_tiles


# ============================================================================
# Tile Loading
# ============================================================================


@st.cache_data(ttl=3600)
def load_tile(tile_file: str) -> gpd.GeoDataFrame:
    """
    Load a single tile from local storage or R2.

    Args:
        tile_file: Relative path to tile file (e.g., "512000/all.parquet")

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
    grid_size = layer_name.split("_")[-1]

    # Get tiles that intersect the bounds
    tiles = get_tiles_for_bounds(bounds, grid_size)

    if not tiles:
        return gpd.GeoDataFrame(columns=list(dict.fromkeys(columns + ["geometry"])))

    # Load and concatenate tiles
    gdfs = []
    for tile in tiles:
        try:
            gdf = load_tile(tile["file"])
            gdfs.append(gdf)
        except Exception as e:
            st.warning(f"Failed to load tile {tile['file']}: {e}")

    if not gdfs:
        return gpd.GeoDataFrame(columns=list(dict.fromkeys(columns + ["geometry"])))

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

    # Select only requested columns (avoid duplicating geometry)
    available_cols = [c for c in columns if c in result.columns and c != "geometry"]
    return result[available_cols + ["geometry"]]


# ============================================================================
# Legacy Support (deprecated)
# ============================================================================


@st.cache_resource
def get_brixels_data_source():
    """DEPRECATED: Use load_grid_data_r2() with tile-based loading instead."""
    raise RuntimeError(
        "Legacy GeoPackage loading is deprecated. "
        "Use load_grid_data_r2() with GeoParquet tiles."
    )
