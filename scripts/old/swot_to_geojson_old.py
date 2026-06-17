#!/usr/bin/env python3
"""
swot_to_geojson.py

Purpose:
    Convert one SWOT NetCDF file into a GeoJSON file that can be displayed
    on a web map, such as React Leaflet or MMGIS.

Input:
    A SWOT L3 LR SSH Expert NetCDF file, for example:
    SWOT_L3_LR_SSH_Expert_013_147_20240401T194600_20240401T203727_v3.0.nc

Output:
    A GeoJSON file, for example:
    outputs/swot_pass_147_full_track.geojson

What the GeoJSON contains:
    One LineString feature representing the full SWOT pass track.

Important:
    This first version does NOT visualize SSHA values yet.
    It only extracts the latitude/longitude track from the NetCDF.
    Later, we can add:
        - Gulf Stream clipping
        - swath edge outlines
        - full swath polygons
        - SSHA raster/image export
        - popup metadata
"""

import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr


def lon_360_to_180(lon):
    """
    Convert longitude values from 0–360 format to -180–180 format.

    Why this matters:
        Some satellite datasets store longitude from 0 to 360 degrees.
        Example:
            279 degrees = -81 degrees
            353 degrees = -7 degrees

        Web maps like Leaflet usually expect longitude from -180 to 180.

    Formula:
        ((lon + 180) % 360) - 180

    Input:
        lon: NumPy array of longitude values

    Output:
        NumPy array of converted longitude values
    """
    return ((lon + 180) % 360) - 180


def extract_pass_line(ds):
    """
    Extract an approximate centerline by averaging valid SWOT swath pixels
    across each along-track row.

    This works better than choosing one middle pixel column because SWOT has
    a nadir gap and two KaRIn swaths.
    """
    lat = ds["latitude"].values
    lon = ds["longitude"].values

    lon = lon_360_to_180(lon)

    coords = []

    for row_lon, row_lat in zip(lon, lat):
        valid = np.isfinite(row_lon) & np.isfinite(row_lat)

        if np.sum(valid) < 2:
            continue

        center_lon = float(np.nanmean(row_lon[valid]))
        center_lat = float(np.nanmean(row_lat[valid]))

        coords.append([center_lon, center_lat])

    if len(coords) < 2:
        raise ValueError("Not enough valid points to make a GeoJSON line.")

    return coords


def build_geojson_feature(nc_path, ds, coords, pass_num=None, cycle=None):
    """
    Build a GeoJSON FeatureCollection from the extracted pass line.

    A GeoJSON FeatureCollection is the format Leaflet can load.

    Structure:
        FeatureCollection
            Feature
                properties = metadata shown in popups later
                geometry = LineString coordinates

    Input:
        nc_path: path to the NetCDF file
        ds: xarray Dataset
        coords: list of [longitude, latitude] points
        pass_num: optional SWOT pass number, like 147
        cycle: optional SWOT cycle number, like 013

    Output:
        GeoJSON dictionary
    """

    # This is one map feature: the SWOT pass line.
    feature = {
        "type": "Feature",
        "properties": {
            # These properties can be shown in a Leaflet popup later.
            "name": "SWOT Pass Line",
            "source_file": nc_path.name,
            "pass": pass_num,
            "cycle": cycle,

            # These come from the NetCDF global attributes.
            "time_start": str(ds.attrs.get("time_coverage_start", "")),
            "time_end": str(ds.attrs.get("time_coverage_end", "")),
            "product": ds.attrs.get("title", "SWOT L3 LR SSH Expert"),
            "doi": ds.attrs.get("doi", ""),
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
    }

    # GeoJSON files usually contain a FeatureCollection, even if there is
    # only one feature.
    geojson = {
        "type": "FeatureCollection",
        "features": [feature],
    }

    return geojson


def main():
    """
    Main command-line function.

    This lets you run the script like:

        python scripts/swot_to_geojson.py input_file.nc --output output.geojson

    It:
        1. Reads command-line arguments
        2. Opens the NetCDF file
        3. Extracts the SWOT pass line
        4. Builds GeoJSON
        5. Saves the GeoJSON file
    """

    parser = argparse.ArgumentParser(
        description="Convert a SWOT NetCDF pass track to GeoJSON."
    )

    # Required input NetCDF file.
    parser.add_argument(
        "file",
        help="Path to SWOT NetCDF file.",
    )

    # Optional output path.
    # If not provided, it saves to outputs/swot_pass_line.geojson.
    parser.add_argument(
        "--output",
        default="outputs/swot_pass_line.geojson",
        help="Output GeoJSON path.",
    )

    # Optional metadata: pass number.
    parser.add_argument(
        "--pass-num",
        default=None,
        help="SWOT pass number, e.g. 147.",
    )

    # Optional metadata: cycle number.
    parser.add_argument(
        "--cycle",
        default=None,
        help="SWOT cycle number, e.g. 013.",
    )

    args = parser.parse_args()

    # Convert file paths into absolute paths.
    nc_path = Path(args.file).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    # Stop early if the NetCDF file does not exist.
    if not nc_path.exists():
        raise FileNotFoundError(f"File not found: {nc_path}")

    # Make the output folder if it does not exist.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Opening NetCDF: {nc_path}")

    # Open the SWOT NetCDF file with xarray.
    ds = xr.open_dataset(nc_path)

    # Extract the full pass line coordinates.
    coords = extract_pass_line(ds)

    # Build the GeoJSON object.
    geojson = build_geojson_feature(
        nc_path=nc_path,
        ds=ds,
        coords=coords,
        pass_num=args.pass_num,
        cycle=args.cycle,
    )

    # Write the GeoJSON dictionary to a .geojson file.
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)

    print(f"Saved GeoJSON: {output_path}")
    print(f"Number of line points: {len(coords)}")
    print("Done.")


# This makes sure main() runs when you execute the file directly.
if __name__ == "__main__":
    main()