"""
Sample elevation from Cloud-Optimized GeoTIFF (COG) on demand.

This replaces the pre-computed point grids with on-demand sampling,
providing more flexibility and much smaller storage requirements.
"""

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds


class COGSampler:
    """Sample elevation data from a Cloud-Optimized GeoTIFF."""
    
    def __init__(self, cog_url: str):
        """
        Initialize sampler with COG URL.
        
        Args:
            cog_url: URL or path to COG file (can be HTTP, S3, or local path)
        """
        self.cog_url = cog_url
        self._transformer_to_4326 = Transformer.from_crs(
            "EPSG:3857", "EPSG:4326", always_xy=True
        )
        self._transformer_from_4326 = Transformer.from_crs(
            "EPSG:4326", "EPSG:3857", always_xy=True
        )
    
    def sample_grid(
        self,
        bounds: tuple[float, float, float, float],
        grid_size: int,
        crs: str = "EPSG:3857",
    ) -> dict:
        """
        Sample elevation at regular grid points within bounds.
        
        Args:
            bounds: (minx, miny, maxx, maxy) bounding box
            grid_size: Grid spacing in meters (for EPSG:3857)
            crs: Coordinate system of bounds (default EPSG:3857)
            
        Returns:
            Dictionary with 'x', 'y', 'elevation' arrays
        """
        minx, miny, maxx, maxy = bounds
        
        # Generate grid points in Web Mercator
        x_coords = np.arange(
            np.floor(minx / grid_size) * grid_size,
            np.ceil(maxx / grid_size) * grid_size + grid_size,
            grid_size,
        )
        y_coords = np.arange(
            np.floor(miny / grid_size) * grid_size,
            np.ceil(maxy / grid_size) * grid_size + grid_size,
            grid_size,
        )
        
        # Create meshgrid
        xx, yy = np.meshgrid(x_coords, y_coords)
        x_flat = xx.flatten()
        y_flat = yy.flatten()
        
        # Transform to WGS84 for raster sampling
        lon, lat = self._transformer_to_4326.transform(x_flat, y_flat)
        
        # Sample from COG
        with rasterio.open(self.cog_url) as src:
            # Use appropriate overview based on resolution
            # COG automatically selects best overview for the requested resolution
            elevations = np.array(
                list(src.sample(zip(lon, lat), indexes=1))
            ).flatten()
            
            # Handle nodata
            nodata = src.nodata or -32768
            elevations = np.where(elevations == nodata, 0, elevations)
        
        return {
            "x": x_flat,
            "y": y_flat,
            "elevation": elevations,
        }
    
    def sample_window(
        self,
        bounds: tuple[float, float, float, float],
        width: int,
        height: int,
    ) -> np.ndarray:
        """
        Read elevation data for a window (for raster operations).
        
        Args:
            bounds: (minx, miny, maxx, maxy) in WGS84
            width: Output width in pixels
            height: Output height in pixels
            
        Returns:
            2D numpy array of elevations
        """
        with rasterio.open(self.cog_url) as src:
            window = from_bounds(*bounds, src.transform)
            data = src.read(
                1,
                window=window,
                out_shape=(height, width),
                resampling=rasterio.enums.Resampling.average,
            )
            
            # Handle nodata
            nodata = src.nodata or -32768
            data = np.where(data == nodata, 0, data)
            
        return data


# Example usage for Streamlit app integration
def sample_for_viewport(
    cog_url: str,
    bounds: tuple[float, float, float, float],
    zoom: int,
) -> dict:
    """
    Sample elevation for current map viewport.
    
    Args:
        cog_url: URL to COG file
        bounds: Viewport bounds in EPSG:3857
        zoom: Current zoom level
        
    Returns:
        Dictionary with x, y, elevation arrays
    """
    # Map zoom to grid size (same as existing grid_size_dict)
    grid_size_dict = {
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
    
    grid_size = grid_size_dict.get(zoom, 512000)
    
    sampler = COGSampler(cog_url)
    return sampler.sample_grid(bounds, grid_size)
