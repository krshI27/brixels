"""
Convert GeoPackage to partitioned GeoParquet tiles for efficient cloud loading.

This script:
1. Reads each layer (zoom level) from the GeoPackage
2. Partitions data into geographic tiles (e.g., 10° × 10°)
3. Saves as GeoParquet files organized by zoom/tile
4. Generates a tile index for the app to use

Output structure:
    parquet/
    ├── index.json          # Tile metadata
    ├── 512000/             # Zoom level
    │   ├── tile_-180_-90.parquet
    │   ├── tile_-170_-90.parquet
    │   └── ...
    ├── 256000/
    │   └── ...
    └── ...
"""

import json
import os
import sqlite3
from pathlib import Path

import geopandas as gpd
import numpy as np


def get_layers(gpkg_path: str) -> list[str]:
    """Get all layer names from GeoPackage."""
    conn = sqlite3.connect(gpkg_path)
    cursor = conn.execute("SELECT table_name FROM gpkg_contents")
    layers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return layers


def get_layer_info(gpkg_path: str, layer: str) -> dict:
    """Get row count and bounds for a layer."""
    conn = sqlite3.connect(gpkg_path)
    count = conn.execute(f'SELECT COUNT(*) FROM "{layer}"').fetchone()[0]
    conn.close()
    return {"count": count}


def partition_layer(
    gpkg_path: str,
    layer: str,
    output_dir: Path,
    tile_size: float = 10.0,  # degrees
) -> list[dict]:
    """
    Partition a layer into geographic tiles.

    Args:
        gpkg_path: Path to GeoPackage
        layer: Layer name
        output_dir: Output directory for parquet files
        tile_size: Size of each tile in degrees

    Returns:
        List of tile metadata dicts
    """
    print(f"  Reading layer {layer}...")

    # Read the full layer (we need all data to partition)
    gdf = gpd.read_file(gpkg_path, layer=layer, engine="pyogrio")

    if len(gdf) == 0:
        print(f"  Layer {layer} is empty, skipping")
        return []

    print(f"  {len(gdf):,} features loaded")

    # Ensure we have point geometries
    gdf["x"] = gdf.geometry.x
    gdf["y"] = gdf.geometry.y

    # Calculate tile indices
    gdf["tile_x"] = (np.floor(gdf["x"] / tile_size) * tile_size).astype(int)
    gdf["tile_y"] = (np.floor(gdf["y"] / tile_size) * tile_size).astype(int)

    # Extract grid size from layer name (e.g., "brixels_world_512000" -> "512000")
    grid_size = layer.split("_")[-1]
    layer_dir = output_dir / grid_size
    layer_dir.mkdir(parents=True, exist_ok=True)

    tiles = []

    # Group by tile and save
    for (tile_x, tile_y), tile_gdf in gdf.groupby(["tile_x", "tile_y"]):
        tile_name = f"tile_{int(tile_x)}_{int(tile_y)}.parquet"
        tile_path = layer_dir / tile_name

        # Drop tile columns before saving
        tile_data = tile_gdf.drop(columns=["tile_x", "tile_y", "x", "y"])

        # Save as GeoParquet
        tile_data.to_parquet(tile_path, index=False)

        tiles.append(
            {
                "file": f"{grid_size}/{tile_name}",
                "grid_size": grid_size,
                "min_x": int(tile_x),
                "min_y": int(tile_y),
                "max_x": int(tile_x + tile_size),
                "max_y": int(tile_y + tile_size),
                "count": len(tile_data),
                "size_bytes": tile_path.stat().st_size,
            }
        )

    print(f"  Created {len(tiles)} tiles")
    return tiles


def main():
    # Configuration
    gpkg_path = "/Users/maximiliansperlich/Developer/projects/data/brixels_world_512000-008000.gpkg"
    output_dir = Path(
        "/Users/maximiliansperlich/Developer/projects/data/brixels_parquet"
    )
    tile_size = 10.0  # degrees (adjust for desired tile size)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get all layers
    layers = get_layers(gpkg_path)
    print(f"Found {len(layers)} layers: {layers}")

    # Process each layer
    all_tiles = []

    for layer in layers:
        info = get_layer_info(gpkg_path, layer)
        print(f"\nProcessing {layer} ({info['count']:,} features)...")

        tiles = partition_layer(gpkg_path, layer, output_dir, tile_size)
        all_tiles.extend(tiles)

    # Save tile index
    index = {
        "tile_size_degrees": tile_size,
        "total_tiles": len(all_tiles),
        "grid_sizes": list(set(t["grid_size"] for t in all_tiles)),
        "tiles": all_tiles,
    }

    index_path = output_dir / "index.json"
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)

    print(f"\n✅ Conversion complete!")
    print(f"   Output directory: {output_dir}")
    print(f"   Total tiles: {len(all_tiles)}")
    print(f"   Index file: {index_path}")

    # Calculate total size
    total_size = sum(t["size_bytes"] for t in all_tiles)
    print(f"   Total size: {total_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
