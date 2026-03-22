#!/usr/bin/env python3
"""
Prepare Brixels data for R2 deployment.

Downloads the GeoPackage from R2, converts each grid-size layer
to properly-tiled GeoParquet, then uploads the tiles back to R2.

Usage:
    python scripts/prepare_r2_data.py                # Full pipeline
    python scripts/prepare_r2_data.py --download      # Download GeoPackage only
    python scripts/prepare_r2_data.py --convert       # Convert only (GeoPackage must exist)
    python scripts/prepare_r2_data.py --upload        # Upload only (tiles must exist)
    python scripts/prepare_r2_data.py --columns elevation,depth  # Keep specific columns
"""

import argparse
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
import geopandas as gpd
import numpy as np
from botocore.config import Config
from tqdm import tqdm

# =============================================================================
# Configuration
# =============================================================================

# Tile sizes in EPSG:3857 meters. None = single file (for small layers).
TILE_SIZES = {
    "512000": None,
    "256000": None,
    "128000": 5_000_000,
    "064000": 3_000_000,
    "032000": 2_000_000,
    "016000": 1_000_000,
    "008000": 1_000_000,
}

DEFAULT_COLUMNS = ["elevation"]

GPKG_R2_KEY = "brixels_world.gpkg"
PARQUET_R2_PREFIX = "parquet"

LOCAL_GPKG = Path("/tmp/brixels_world.gpkg")
LOCAL_GPKG_ALT = Path(
    "/Users/maximiliansperlich/Developer/projects/data/brixels_world_512000-008000.gpkg"
)
LOCAL_OUTPUT = Path("/tmp/brixels_parquet_v2")


# =============================================================================
# R2 Helpers
# =============================================================================


def load_secrets() -> dict:
    """Parse secrets.toml, skipping comments."""
    secrets = {}
    secrets_path = Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
    with open(secrets_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                secrets[key.strip()] = val.strip().strip('"')
    return secrets


def get_r2_client(secrets: dict):
    return boto3.client(
        "s3",
        endpoint_url=secrets["CLOUDFLARE_S3_API"],
        aws_access_key_id=secrets["R2_ACCESS_ID"],
        aws_secret_access_key=secrets["R2_SECRET_ACCESS_KEY"],
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"}),
    )


# =============================================================================
# Download
# =============================================================================


def download_gpkg(r2, bucket: str) -> Path:
    """Download GeoPackage from R2, or use local copy if available."""
    if LOCAL_GPKG_ALT.exists():
        size_mb = LOCAL_GPKG_ALT.stat().st_size / 1024 / 1024
        print(f"Using local GeoPackage ({size_mb:.0f} MB): {LOCAL_GPKG_ALT}")
        return LOCAL_GPKG_ALT

    if LOCAL_GPKG.exists():
        size_mb = LOCAL_GPKG.stat().st_size / 1024 / 1024
        print(f"GeoPackage already downloaded ({size_mb:.0f} MB): {LOCAL_GPKG}")
        return LOCAL_GPKG

    head = r2.head_object(Bucket=bucket, Key=GPKG_R2_KEY)
    size_mb = head["ContentLength"] / 1024 / 1024
    print(f"Downloading {GPKG_R2_KEY} from R2 ({size_mb:.0f} MB)...")
    r2.download_file(bucket, GPKG_R2_KEY, str(LOCAL_GPKG))
    print(f"  Saved to {LOCAL_GPKG}")
    return LOCAL_GPKG


# =============================================================================
# Conversion
# =============================================================================


def get_layers(gpkg_path: str) -> list[str]:
    """Get brixels layer names from GeoPackage, coarsest first."""
    conn = sqlite3.connect(gpkg_path)
    cursor = conn.execute("SELECT table_name FROM gpkg_contents")
    layers = sorted(
        [r[0] for r in cursor.fetchall() if r[0].startswith("brixels_world_")],
        key=lambda x: int(x.split("_")[-1]),
        reverse=True,
    )
    conn.close()
    return layers


def partition_layer(
    gpkg_path: str,
    layer: str,
    output_dir: Path,
    columns: list[str],
) -> list[dict]:
    """Read a GeoPackage layer and write properly-tiled GeoParquet files."""
    grid_size = layer.split("_")[-1]
    tile_size_m = TILE_SIZES.get(grid_size)
    layer_dir = output_dir / grid_size
    layer_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Layer: {layer} (grid_size={grid_size})")
    print(f"  Tile size: {'single file' if tile_size_m is None else f'{tile_size_m/1000:.0f} km'}")
    print(f"{'='*60}")

    gdf = gpd.read_file(gpkg_path, layer=layer, engine="pyogrio")
    if len(gdf) == 0:
        print("  Empty layer, skipping")
        return []

    # Keep only requested columns + geometry
    available = [c for c in columns if c in gdf.columns]
    gdf = gdf[available + ["geometry"]]
    print(f"  {len(gdf):,} points, columns: {available}")

    # --- Single file ---
    if tile_size_m is None:
        path = layer_dir / "all.parquet"
        gdf.to_parquet(path, index=False, compression="snappy")
        tile_meta = {
            "file": f"{grid_size}/all.parquet",
            "grid_size": grid_size,
            "min_x": float(gdf.geometry.x.min()),
            "min_y": float(gdf.geometry.y.min()),
            "max_x": float(gdf.geometry.x.max()),
            "max_y": float(gdf.geometry.y.max()),
            "count": len(gdf),
            "size_bytes": path.stat().st_size,
        }
        print(f"  → 1 file, {path.stat().st_size / 1024:.0f} KB")
        return [tile_meta]

    # --- Geographic tiling ---
    x = gdf.geometry.x.values
    y = gdf.geometry.y.values
    gdf["_tx"] = (np.floor(x / tile_size_m) * tile_size_m).astype(np.int64)
    gdf["_ty"] = (np.floor(y / tile_size_m) * tile_size_m).astype(np.int64)

    tiles = []
    groups = gdf.groupby(["_tx", "_ty"], sort=False)
    print(f"  Partitioning into {groups.ngroups} tiles...")

    for (tx, ty), group in tqdm(groups, total=groups.ngroups, desc=f"  {grid_size}"):
        tile_name = f"tile_{int(tx)}_{int(ty)}.parquet"
        path = layer_dir / tile_name
        group.drop(columns=["_tx", "_ty"]).to_parquet(
            path, index=False, compression="snappy"
        )
        tiles.append(
            {
                "file": f"{grid_size}/{tile_name}",
                "grid_size": grid_size,
                "min_x": float(tx),
                "min_y": float(ty),
                "max_x": float(tx + tile_size_m),
                "max_y": float(ty + tile_size_m),
                "count": len(group),
                "size_bytes": path.stat().st_size,
            }
        )

    total_mb = sum(t["size_bytes"] for t in tiles) / 1024 / 1024
    print(f"  → {len(tiles)} tiles, {total_mb:.1f} MB total")
    return tiles


def convert(gpkg_path: Path, columns: list[str]) -> dict:
    """Convert all layers in a GeoPackage to tiled GeoParquet."""
    LOCAL_OUTPUT.mkdir(parents=True, exist_ok=True)

    layers = get_layers(str(gpkg_path))
    print(f"\nFound {len(layers)} layers: {[l.split('_')[-1] for l in layers]}")

    all_tiles = []
    for layer in layers:
        tiles = partition_layer(str(gpkg_path), layer, LOCAL_OUTPUT, columns)
        all_tiles.extend(tiles)

    index = {
        "coordinate_system": "EPSG:3857",
        "tile_sizes_m": TILE_SIZES,
        "total_tiles": len(all_tiles),
        "grid_sizes": sorted(set(t["grid_size"] for t in all_tiles)),
        "tiles": all_tiles,
    }
    with open(LOCAL_OUTPUT / "index.json", "w") as f:
        json.dump(index, f)

    total_mb = sum(t["size_bytes"] for t in all_tiles) / 1024 / 1024
    print(f"\nConversion complete: {len(all_tiles)} tiles, {total_mb:.1f} MB")
    return index


# =============================================================================
# Upload
# =============================================================================


def upload_to_r2(r2, bucket: str):
    """Upload all tiles and index.json to R2 with parallel uploads."""
    files = sorted(LOCAL_OUTPUT.rglob("*.parquet")) + [LOCAL_OUTPUT / "index.json"]
    print(f"\nUploading {len(files)} files to R2 (bucket={bucket})...")

    def upload_one(filepath: Path):
        key = f"{PARQUET_R2_PREFIX}/{filepath.relative_to(LOCAL_OUTPUT)}"
        r2.upload_file(str(filepath), bucket, key)
        return filepath

    with tqdm(total=len(files), desc="  Uploading") as pbar:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(upload_one, f) for f in files]
            for fut in as_completed(futures):
                fut.result()
                pbar.update(1)

    print("  Upload complete!")


# =============================================================================
# Cleanup: remove old GeoPackage from R2 (optional)
# =============================================================================


def cleanup_old_gpkg(r2, bucket: str):
    """Optionally remove the large GeoPackage from R2 after tiles are uploaded."""
    response = input(
        "\nRemove the old GeoPackage from R2 to save storage? [y/N] "
    ).strip()
    if response.lower() == "y":
        r2.delete_object(Bucket=bucket, Key=GPKG_R2_KEY)
        print(f"  Deleted {GPKG_R2_KEY} from R2")
    else:
        print(f"  Keeping {GPKG_R2_KEY} in R2")


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Prepare Brixels data for R2")
    parser.add_argument("--download", action="store_true", help="Download GeoPackage only")
    parser.add_argument("--convert", action="store_true", help="Convert to GeoParquet only")
    parser.add_argument("--upload", action="store_true", help="Upload tiles to R2 only")
    parser.add_argument(
        "--columns",
        default=",".join(DEFAULT_COLUMNS),
        help="Comma-separated columns to keep (default: elevation)",
    )
    args = parser.parse_args()

    run_all = not (args.download or args.convert or args.upload)
    columns = [c.strip() for c in args.columns.split(",")]

    secrets = load_secrets()
    r2 = get_r2_client(secrets)
    bucket = secrets.get("R2_BUCKET_NAME", "brixels-data")

    if run_all or args.download:
        gpkg_path = download_gpkg(r2, bucket)
    else:
        gpkg_path = LOCAL_GPKG_ALT if LOCAL_GPKG_ALT.exists() else LOCAL_GPKG

    if run_all or args.convert:
        if not gpkg_path.exists():
            print(f"ERROR: GeoPackage not found at {gpkg_path}", file=sys.stderr)
            print("  Run with --download first.", file=sys.stderr)
            sys.exit(1)
        convert(gpkg_path, columns)

    if run_all or args.upload:
        if not LOCAL_OUTPUT.exists():
            print(f"ERROR: No tiles at {LOCAL_OUTPUT}", file=sys.stderr)
            print("  Run with --convert first.", file=sys.stderr)
            sys.exit(1)
        upload_to_r2(r2, bucket)

    if run_all:
        cleanup_old_gpkg(r2, bucket)

    print("\nDone!")


if __name__ == "__main__":
    main()
