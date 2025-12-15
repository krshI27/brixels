"""
Cloudflare R2 storage integration for Brixels.

Provides data loading from R2 with local file fallback for development.
"""

import os
from functools import lru_cache
from io import BytesIO

import boto3
import geopandas as gpd
import streamlit as st
from botocore.config import Config


def get_r2_client():
    """Create R2 client using Streamlit secrets."""
    # Support both naming conventions
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


def is_local_dev() -> bool:
    """Check if running in local development mode with local data."""
    local_path = "/data/brixels_world_512000-008000.gpkg"
    return os.path.exists(local_path)


@st.cache_resource
def get_brixels_data_source():
    """
    Get the data source for brixels.
    Returns local path if available, otherwise downloads from R2.
    """
    local_path = "/data/brixels_world_512000-008000.gpkg"

    if is_local_dev():
        return local_path

    # Download from R2 to temp location
    r2 = get_r2_client()
    bucket = st.secrets.get("R2_BUCKET_NAME", "brixels-data")

    # Create temp directory if needed
    temp_path = "/tmp/brixels_world.gpkg"

    if not os.path.exists(temp_path):
        with st.spinner("Loading world data from cloud storage..."):
            r2.download_file(bucket, "brixels_world.gpkg", temp_path)

    return temp_path


def load_grid_data_r2(layer_name: str, bounds: tuple, columns: list):
    """
    Load grid data from R2 or local file.

    Args:
        layer_name: GeoPackage layer name
        bounds: Bounding box tuple (minx, miny, maxx, maxy)
        columns: List of columns to load

    Returns:
        GeoDataFrame with requested data
    """
    data_path = get_brixels_data_source()

    return gpd.read_file(
        data_path,
        layer=layer_name,
        bbox=bounds,
        columns=columns,
        engine="pyogrio",
    )
