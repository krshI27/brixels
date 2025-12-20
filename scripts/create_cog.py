"""
Convert NASADEM to Cloud-Optimized GeoTIFF (COG) for efficient cloud loading.

COG benefits:
- Built-in overviews (pyramids) for zoom levels
- HTTP range requests for partial reads
- Standard format with wide tool support
- ~50-100MB vs 500MB+ for point grids

Usage:
    python create_cog.py --input /path/to/NASADEM.vrt --output /path/to/nasadem_cog.tif
"""

import argparse
from pathlib import Path

from osgeo import gdal


def create_cog(input_path: str, output_path: str, overview_levels: list[int] = None):
    """
    Create a Cloud-Optimized GeoTIFF from input raster.
    
    Args:
        input_path: Path to input raster (VRT, TIF, etc.)
        output_path: Path for output COG
        overview_levels: Overview levels (default: [2, 4, 8, 16, 32, 64])
    """
    if overview_levels is None:
        overview_levels = [2, 4, 8, 16, 32, 64]
    
    print(f"Creating COG from {input_path}...")
    
    # Open source
    src = gdal.Open(input_path)
    if src is None:
        raise RuntimeError(f"Could not open {input_path}")
    
    print(f"  Source: {src.RasterXSize} x {src.RasterYSize}")
    
    # Create COG with GDAL translate
    # COG profile: tiled, compressed, with overviews
    translate_options = gdal.TranslateOptions(
        format="COG",
        creationOptions=[
            "COMPRESS=DEFLATE",
            "PREDICTOR=2",
            "BIGTIFF=IF_SAFER",
            "OVERVIEWS=AUTO",
            "OVERVIEW_RESAMPLING=AVERAGE",
            "BLOCKSIZE=512",
        ],
    )
    
    print("  Converting to COG (this may take a while)...")
    gdal.Translate(output_path, src, options=translate_options)
    
    # Verify
    cog = gdal.Open(output_path)
    if cog is None:
        raise RuntimeError(f"Failed to create COG at {output_path}")
    
    size_mb = Path(output_path).stat().st_size / 1024 / 1024
    print(f"  Created: {output_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Dimensions: {cog.RasterXSize} x {cog.RasterYSize}")
    
    # Check overviews
    band = cog.GetRasterBand(1)
    overview_count = band.GetOverviewCount()
    print(f"  Overviews: {overview_count}")
    
    cog = None
    src = None
    
    print("Done!")


def main():
    parser = argparse.ArgumentParser(description="Create Cloud-Optimized GeoTIFF")
    parser.add_argument("--input", "-i", required=True, help="Input raster path")
    parser.add_argument("--output", "-o", required=True, help="Output COG path")
    args = parser.parse_args()
    
    create_cog(args.input, args.output)


if __name__ == "__main__":
    main()
