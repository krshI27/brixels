from pathlib import Path

import numpy as np
import rasterio

def create_rasterio_dataset(image_array):
    # Get image shape
    height, width, count = image_array.shape
    dtype = image_array.dtype
    crs = "EPSG:3857"

    # EPSG:3857 bounds in meters
    west = -20037508.34
    south = -20048966.1
    east = 20037508.34
    north = 20048966.1

    # Create transformation matrix
    transform = rasterio.transform.from_bounds(west, south, east, north, width, height)

    # Create rasterio MemoryFile
    with rasterio.MemoryFile() as memfile:
        # Create rasterio dataset
        dataset = memfile.open(
            driver="GTiff",
            height=height,
            width=width,
            count=count,
            dtype=dtype,
            crs=crs,
            transform=transform,
        )

        # Write image array to dataset
        dataset.write(image_array, indexes=[1, 2, 3])

        # Save dataset to file
        memfile.seek(0)
        with rasterio.open("output.tif", "w", **dataset.profile) as dst:
            dst.write(memfile.read())

    return dataset


if __name__ == "__main__":
    # Read image file
    image_path = Path("image.jpg")
    image_array = read_image(image_path)

    # Create rasterio dataset
    dataset = create_rasterio_dataset(image_array)
    print("Rasterio dataset created successfully")
