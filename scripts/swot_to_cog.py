#!/usr/bin/env python3
"""
swot_to_cog.py

Convert SWOT L3 LR SSH NetCDF swath data into a Cloud Optimized GeoTIFF.

This version is intentionally minimal-processing.

Pipeline:
    SWOT NetCDF
    -> read latitude, longitude, SSHA
    -> convert longitude to -180 to 180
    -> optionally mask using quality_flag == 0
    -> optionally clip to a bounding box
    -> directly place real SWOT values onto a regular raster grid
    -> leave empty cells as nodata
    -> write COG to frontend/public/data

Important:
    This script does NOT interpolate.
    This script does NOT fill holes.
    This script does NOT smooth the data.

Why?
    For a science-style visualization, we want to avoid inventing values
    between real SWOT measurements.

Example for Jacob's Gulf Stream AOI:

    python scripts/swot_to_cog.py \
      ~/Documents/MOSAICS-2026/SWOT-Data/JACOBS_UNSMOOTHED_FILE.nc \
      --variable ssha_unfiltered \
      --output frontend/public/data/swot_pass_91_unsmoothed_ssha_unfiltered_raw_cog.tif \
      --resolution-deg 0.0025 \
      --bbox -82 23 -69 42

Bounding box order:
    --bbox WEST SOUTH EAST NORTH

Jacob gave:
    S, W, N, E = 23, -82, 42, -69

For this script:
    --bbox -82 23 -69 42
"""

import argparse
from pathlib import Path

import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.shutil import copy as rio_copy


def lon_360_to_180(lon):
    """
    Convert longitude from 0–360 degrees to -180–180 degrees.

    Example:
        278 degrees becomes -82 degrees.

    Web maps usually expect longitude in -180 to 180 format.
    """
    return ((lon + 180) % 360) - 180


def main():
    parser = argparse.ArgumentParser(
        description="Convert SWOT NetCDF SSHA swath into a Cloud Optimized GeoTIFF."
    )

    parser.add_argument(
        "file",
        help="Path to SWOT NetCDF file.",
    )

    parser.add_argument(
        "--variable",
        default="ssha_unfiltered",
        help="Variable to export, e.g. ssha_unfiltered, ssha_filtered, or ssha_unedited.",
    )

    parser.add_argument(
        "--output",
        default="frontend/public/data/swot_ssha_cog.tif",
        help="Output COG GeoTIFF path.",
    )

    parser.add_argument(
        "--resolution-deg",
        type=float,
        default=0.0025,
        help=(
            "Output raster resolution in degrees. "
            "Smaller = finer-looking raster but larger/slower file. "
            "0.0025 is roughly 250 m near the equator. "
            "0.005 is roughly 500 m near the equator."
        ),
    )

    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help=(
            "Optional bounding box clip in WEST SOUTH EAST NORTH order. "
            "Example for Jacob Gulf Stream AOI: --bbox -82 23 -69 42"
        ),
    )

    parser.add_argument(
        "--quality-mask",
        action="store_true",
        help=(
            "Use only quality_flag == 0 pixels if quality_flag exists. "
            "If omitted, all finite SSHA values are used."
        ),
    )

    args = parser.parse_args()

    nc_path = Path(args.file).expanduser().resolve()
    output_cog = Path(args.output).expanduser().resolve()
    output_cog.parent.mkdir(parents=True, exist_ok=True)

    temp_tif = output_cog.with_name(output_cog.stem + "_temp.tif")

    print(f"Opening NetCDF: {nc_path}")

    ds = xr.open_dataset(nc_path, mask_and_scale=True)

    if args.variable not in ds:
        raise ValueError(
            f"Variable '{args.variable}' not found. "
            f"Available variables: {list(ds.data_vars)}"
        )

    if "latitude" not in ds or "longitude" not in ds:
        raise ValueError(
            "This script expected variables named 'latitude' and 'longitude'. "
            "Open the NetCDF and inspect variable names if this fails."
        )

    print(f"Using variable: {args.variable}")

    # Read coordinates and data.
    lat = ds["latitude"].values
    lon = ds["longitude"].values
    data = ds[args.variable].values

    # Convert longitudes into web-map format.
    lon = lon_360_to_180(lon)

    # Optional quality filtering.
    # For SWOT L3 Expert/Unsmoothed, quality_flag usually exists.
    # quality_flag == 0 means valid/good.
    if args.quality_mask:
        if "quality_flag" in ds:
            print("Applying quality_flag == 0 mask...")
            quality_flag = ds["quality_flag"].values
            data = np.where(quality_flag == 0, data, np.nan)
        else:
            print("Warning: --quality-mask was requested, but quality_flag was not found.")

    # Remove extreme values for safety.
    # This does not control the color ramp.
    # The React map controls color range separately.
    data = np.where((data > -2.0) & (data < 2.0), data, np.nan)

    # Flatten the SWOT swath arrays.
    lon_flat = lon.ravel()
    lat_flat = lat.ravel()
    data_flat = data.ravel()

    # Keep only real finite values.
    valid = (
        np.isfinite(lon_flat)
        & np.isfinite(lat_flat)
        & np.isfinite(data_flat)
    )

    # Optional bbox clip.
    if args.bbox is not None:
        west_clip, south_clip, east_clip, north_clip = args.bbox

        print("Applying bounding box clip:")
        print(f"  west:  {west_clip}")
        print(f"  south: {south_clip}")
        print(f"  east:  {east_clip}")
        print(f"  north: {north_clip}")

        bbox_mask = (
            (lon_flat >= west_clip)
            & (lon_flat <= east_clip)
            & (lat_flat >= south_clip)
            & (lat_flat <= north_clip)
        )

        valid = valid & bbox_mask

    lon_valid = lon_flat[valid]
    lat_valid = lat_flat[valid]
    data_valid = data_flat[valid]

    if len(data_valid) == 0:
        raise ValueError(
            f"No valid data values found for variable {args.variable}. "
            "Check the variable name, bbox, and quality mask."
        )

    # Use bounds of the valid data after clipping.
    west = float(np.nanmin(lon_valid))
    east = float(np.nanmax(lon_valid))
    south = float(np.nanmin(lat_valid))
    north = float(np.nanmax(lat_valid))

    print("Output data bounds:")
    print(f"  west:  {west}")
    print(f"  east:  {east}")
    print(f"  south: {south}")
    print(f"  north: {north}")

    resolution = args.resolution_deg

    width = int(np.ceil((east - west) / resolution))
    height = int(np.ceil((north - south) / resolution))

    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid output raster size: {width} x {height}")

    print(f"Output raster size: {width} x {height}")
    print(f"Resolution: {resolution} degrees")

    print("Directly rasterizing SWOT points without interpolation or hole filling...")

    # Start with an empty raster.
    # Every cell remains NaN unless a real SWOT measurement falls into it.
    grid_data = np.full((height, width), np.nan, dtype="float32")

    # Convert each SWOT lon/lat point into a raster column/row.
    #
    # Column:
    #   west -> 0
    #   east -> width - 1
    #
    # Row for now:
    #   south -> 0
    #   north -> height - 1
    #
    # We flip the raster later because GeoTIFF rows are stored north-to-south.
    col = np.floor((lon_valid - west) / resolution).astype(int)
    row = np.floor((lat_valid - south) / resolution).astype(int)

    inside = (
        (col >= 0)
        & (col < width)
        & (row >= 0)
        & (row < height)
    )

    col = col[inside]
    row = row[inside]
    values = data_valid[inside]

    print(f"Valid SWOT points inside raster: {len(values)}")

    if len(values) == 0:
        raise ValueError("No SWOT points landed inside the output raster.")

    # If multiple real SWOT points land in the same raster cell,
    # average them. This is NOT interpolation; it only combines real
    # measurements that occupy the same output cell.
    sum_grid = np.zeros((height, width), dtype="float64")
    count_grid = np.zeros((height, width), dtype="int32")

    np.add.at(sum_grid, (row, col), values)
    np.add.at(count_grid, (row, col), 1)

    has_data = count_grid > 0
    grid_data[has_data] = (sum_grid[has_data] / count_grid[has_data]).astype("float32")

    filled_cells = int(np.count_nonzero(has_data))
    total_cells = int(height * width)
    print(f"Filled raster cells: {filled_cells} / {total_cells}")

    # GeoTIFF rows must go north-to-south.
    # Our row calculation was south-to-north, so flip vertically.
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
            product=ds.attrs.get("title", "SWOT L3 LR SSH"),
            doi=ds.attrs.get("doi", ""),
            bbox=str(args.bbox) if args.bbox is not None else "",
            resolution_deg=str(args.resolution_deg),
            quality_mask=str(args.quality_mask),
            processing="direct_raster_no_interpolation_no_hole_filling",
        )

    print(f"Converting to Cloud Optimized GeoTIFF: {output_cog}")

    rio_copy(
        temp_tif,
        output_cog,
        driver="COG",
        compress="deflate",
        predictor=2,
        blocksize=256,
        overview_resampling="nearest",
    )

    temp_tif.unlink(missing_ok=True)

    print(f"Saved COG: {output_cog}")
    print("Done.")


if __name__ == "__main__":
    main()