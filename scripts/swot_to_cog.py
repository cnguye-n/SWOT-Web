#!/usr/bin/env python3
"""
swot_to_cog.py

Convert SWOT L3 LR SSH Expert NetCDF swath data into a Cloud Optimized GeoTIFF.

Pipeline:
    SWOT NetCDF
    -> read latitude, longitude, SSHA
    -> convert longitude to -180 to 180
    -> optionally mask quality_flag != 0
    -> interpolate onto regular EPSG:4326 lon/lat grid
    -> mask cells too far from real SWOT pixels
    -> write COG to frontend/public/data
"""

import argparse
from pathlib import Path

import numpy as np
import xarray as xr
from scipy.interpolate import griddata
from scipy.spatial import cKDTree
import rasterio
from rasterio.transform import from_bounds
from rasterio.shutil import copy as rio_copy


def lon_360_to_180(lon):
    """Convert longitude from 0–360 to -180–180."""
    return ((lon + 180) % 360) - 180


def main():
    parser = argparse.ArgumentParser(
        description="Convert SWOT NetCDF SSHA swath into a Cloud Optimized GeoTIFF."
    )

    parser.add_argument("file", help="Path to SWOT NetCDF file.")

    parser.add_argument(
        "--variable",
        default="ssha_unfiltered",
        help="Variable to export, e.g. ssha_unfiltered or ssha_filtered.",
    )

    parser.add_argument(
        "--output",
        default="frontend/public/data/swot_pass_147_ssha_unfiltered_cog.tif",
        help="Output COG GeoTIFF path.",
    )

    parser.add_argument(
        "--resolution-deg",
        type=float,
        default=0.02,
        help="Output raster resolution in degrees. 0.02 is about 2 km.",
    )

    parser.add_argument(
        "--max-distance-deg",
        type=float,
        default=0.04,
        help="Maximum distance from real SWOT pixel before output is set to nodata.",
    )

    parser.add_argument(
        "--quality-mask",
        action="store_true",
        help="Use quality_flag == 0 only.",
    )

    args = parser.parse_args()

    nc_path = Path(args.file).expanduser().resolve()
    output_cog = Path(args.output).expanduser().resolve()
    output_cog.parent.mkdir(parents=True, exist_ok=True)

    temp_tif = output_cog.with_name(output_cog.stem + "_temp.tif")

    print(f"Opening NetCDF: {nc_path}")

    ds = xr.open_dataset(nc_path, mask_and_scale=True)

    if args.variable not in ds:
        raise ValueError(f"Variable '{args.variable}' not found. Available variables: {list(ds.data_vars)}")

    lat = ds["latitude"].values
    lon = ds["longitude"].values
    data = ds[args.variable].values

    lon = lon_360_to_180(lon)

    if args.quality_mask and "quality_flag" in ds:
        print("Applying quality_flag == 0 mask...")
        quality_flag = ds["quality_flag"].values
        data = np.where(quality_flag == 0, data, np.nan)

    # Remove extreme values for safety.
    data = np.where((data > -2.0) & (data < 2.0), data, np.nan)

    lon_flat = lon.ravel()
    lat_flat = lat.ravel()
    data_flat = data.ravel()

    valid = (
        np.isfinite(lon_flat)
        & np.isfinite(lat_flat)
        & np.isfinite(data_flat)
    )

    lon_valid = lon_flat[valid]
    lat_valid = lat_flat[valid]
    data_valid = data_flat[valid]

    if len(data_valid) == 0:
        raise ValueError(f"No valid data values found for variable {args.variable}")

    west = float(np.nanmin(lon_valid))
    east = float(np.nanmax(lon_valid))
    south = float(np.nanmin(lat_valid))
    north = float(np.nanmax(lat_valid))

    print("Swath bounds:")
    print(f"  west:  {west}")
    print(f"  east:  {east}")
    print(f"  south: {south}")
    print(f"  north: {north}")

    resolution = args.resolution_deg

    width = int(np.ceil((east - west) / resolution))
    height = int(np.ceil((north - south) / resolution))

    print(f"Output raster size: {width} x {height}")
    print(f"Resolution: {resolution} degrees")

    grid_lon = np.linspace(west, east, width)
    grid_lat = np.linspace(south, north, height)

    grid_lon_2d, grid_lat_2d = np.meshgrid(grid_lon, grid_lat)

    print("Interpolating SWOT swath to regular lon/lat raster grid...")

    grid_data_linear = griddata(
        points=(lon_valid, lat_valid),
        values=data_valid,
        xi=(grid_lon_2d, grid_lat_2d),
        method="linear",
    )

    grid_data_nearest = griddata(
        points=(lon_valid, lat_valid),
        values=data_valid,
        xi=(grid_lon_2d, grid_lat_2d),
        method="nearest",
    )

    # Use linear where available, nearest only for small holes.
    grid_data = np.where(np.isfinite(grid_data_linear), grid_data_linear, grid_data_nearest)

    print("Masking cells outside real SWOT swath ribbon...")

    tree = cKDTree(np.column_stack([lon_valid, lat_valid]))
    distances, _ = tree.query(
        np.column_stack([grid_lon_2d.ravel(), grid_lat_2d.ravel()]),
        k=1,
    )
    distance_grid = distances.reshape(grid_lon_2d.shape)

    grid_data[distance_grid > args.max_distance_deg] = np.nan

    # GeoTIFF rows go north to south.
    grid_data = np.flipud(grid_data)

    nodata = -9999.0
    grid_data = np.where(np.isfinite(grid_data), grid_data, nodata).astype("float32")

    transform = from_bounds(west, south, east, north, width, height)

    print(f"Writing temporary GeoTIFF: {temp_tif}")

    with rasterio.open(
        temp_tif,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
        predictor=2,
    ) as dst:
        dst.write(grid_data, 1)
        dst.update_tags(
            variable=args.variable,
            source_file=nc_path.name,
            time_start=str(ds.attrs.get("time_coverage_start", "")),
            time_end=str(ds.attrs.get("time_coverage_end", "")),
            units=ds[args.variable].attrs.get("units", "m"),
            product=ds.attrs.get("title", "SWOT L3 LR SSH Expert"),
            doi=ds.attrs.get("doi", ""),
        )

    print(f"Converting to Cloud Optimized GeoTIFF: {output_cog}")

    rio_copy(
        temp_tif,
        output_cog,
        driver="COG",
        compress="deflate",
        predictor=2,
        blocksize=256,
        overview_resampling="average",
    )

    temp_tif.unlink(missing_ok=True)

    print(f"Saved COG: {output_cog}")
    print("Done.")


if __name__ == "__main__":
    main()