#!/usr/bin/env python3
"""Build one lightweight GeoJSON catalog of full SWOT pass tracks.

The catalog is the first layer loaded by the React-Leaflet map. Each pass is
one GeoJSON feature. The feature properties contain the browser URLs for that
pass's nadir GeoJSON and SSHA COG, but those larger detail files are not loaded
until the user clicks the pass.

Example for all NetCDF files in one folder:

    python scripts/swot_to_geojson.py \
      ~/Documents/MOSAICS-2026/SWOT-Data/*.nc \
      --output frontend/public/data/swot_full_tracks.geojson \
      --stride 10

The shell expands ``*.nc`` into multiple input paths. A stride of 10 keeps the
world-scale orbit lines light enough for the browser while preserving their
shape. It does not affect the scientific COG data.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

PASS_PATTERN = re.compile(
    r"_(?P<cycle>\d{3})_(?P<pass>\d{3})_"
    r"(?P<start>\d{8}T\d{6})_(?P<end>\d{8}T\d{6})_"
)


def wrap_longitudes(longitude: np.ndarray) -> np.ndarray:
    """Convert longitudes to Leaflet's expected [-180, 180) range."""
    return ((longitude + 180.0) % 360.0) - 180.0


def circular_mean_longitude(longitudes: np.ndarray) -> float:
    """Average longitude correctly when source points approach the dateline."""
    radians = np.deg2rad(longitudes)
    mean_sin = np.mean(np.sin(radians))
    mean_cos = np.mean(np.cos(radians))
    return float(np.rad2deg(np.arctan2(mean_sin, mean_cos)))


def parse_filename_metadata(path: Path) -> dict[str, str]:
    """Read cycle, pass, and file timestamps from a standard SWOT filename."""
    match = PASS_PATTERN.search(path.name)
    if not match:
        raise ValueError(
            "Could not find cycle/pass/timestamps in filename: "
            f"{path.name}"
        )
    return match.groupdict()


def extract_centerline(ds: xr.Dataset, stride: int) -> list[list[float]]:
    """Extract a lightweight centerline from the native 2-D SWOT swath.

    A circular longitude mean avoids the false center produced by a regular
    arithmetic mean near ±180 degrees. ``stride`` only simplifies the overview
    line; the nadir and COG retain their own full detail.
    """
    longitude = wrap_longitudes(
        np.asarray(ds["longitude"].values, dtype=np.float64)
    )
    latitude = np.asarray(ds["latitude"].values, dtype=np.float64)

    if longitude.shape != latitude.shape or longitude.ndim != 2:
        raise ValueError(
            "longitude and latitude must be matching 2-D arrays; got "
            f"{longitude.shape} and {latitude.shape}."
        )

    coordinates: list[list[float]] = []

    for row_index in range(0, longitude.shape[0], stride):
        row_lon = longitude[row_index]
        row_lat = latitude[row_index]
        valid = (
            np.isfinite(row_lon)
            & np.isfinite(row_lat)
            & (row_lat >= -90.0)
            & (row_lat <= 90.0)
        )

        if np.count_nonzero(valid) < 2:
            continue

        coordinates.append(
            [
                circular_mean_longitude(row_lon[valid]),
                float(np.mean(row_lat[valid])),
            ]
        )

    # Always retain the final valid row so the overview reaches the pass end.
    final_lon = longitude[-1]
    final_lat = latitude[-1]
    final_valid = (
        np.isfinite(final_lon)
        & np.isfinite(final_lat)
        & (final_lat >= -90.0)
        & (final_lat <= 90.0)
    )
    if np.count_nonzero(final_valid) >= 2:
        final_coordinate = [
            circular_mean_longitude(final_lon[final_valid]),
            float(np.mean(final_lat[final_valid])),
        ]
        if not coordinates or final_coordinate != coordinates[-1]:
            coordinates.append(final_coordinate)

    if len(coordinates) < 2:
        raise ValueError("Not enough valid rows to construct a pass line.")

    return coordinates


def split_at_antimeridian(
    coordinates: list[list[float]],
) -> list[list[list[float]]]:
    """Split a line where longitude jumps across ±180 degrees.

    Without this split, Leaflet can draw an incorrect horizontal line across
    the entire world when a pass crosses the antimeridian.
    """
    segments: list[list[list[float]]] = []
    current: list[list[float]] = [coordinates[0]]

    for previous, coordinate in zip(coordinates, coordinates[1:]):
        if abs(coordinate[0] - previous[0]) > 180.0:
            if len(current) >= 2:
                segments.append(current)
            current = [coordinate]
        else:
            current.append(coordinate)

    if len(current) >= 2:
        segments.append(current)

    if not segments:
        raise ValueError("Antimeridian splitting removed every line segment.")

    return segments


def line_geometry(segments: list[list[list[float]]]) -> dict[str, Any]:
    """Use LineString for one segment or MultiLineString for a dateline pass."""
    if len(segments) == 1:
        return {"type": "LineString", "coordinates": segments[0]}
    return {"type": "MultiLineString", "coordinates": segments}


def build_feature(
    nc_path: Path,
    ds: xr.Dataset,
    stride: int,
    browser_data_prefix: str,
    variable: str,
) -> dict[str, Any]:
    """Create one catalog feature for one SWOT NetCDF pass."""
    metadata = parse_filename_metadata(nc_path)
    cycle = metadata["cycle"]
    pass_number = metadata["pass"]
    pass_id = f"{cycle}-{pass_number}"

    coordinates = extract_centerline(ds, stride=stride)
    segments = split_at_antimeridian(coordinates)

    prefix = browser_data_prefix.rstrip("/")
    base_name = f"swot_cycle_{cycle}_pass_{pass_number}"

    return {
        "type": "Feature",
        "properties": {
            "id": pass_id,
            "name": f"SWOT Cycle {cycle} · Pass {pass_number}",
            "source_file": nc_path.name,
            "cycle": cycle,
            "pass": pass_number,
            "time_start": str(
                ds.attrs.get("time_coverage_start", metadata["start"])
            ),
            "time_end": str(
                ds.attrs.get("time_coverage_end", metadata["end"])
            ),
            "product": str(
                ds.attrs.get("title", "SWOT L3 LR SSH Expert")
            ),
            "variable": variable,
            "nadir_url": f"{prefix}/{base_name}_nadir.geojson",
            "cog_url": f"{prefix}/{base_name}_{variable}_cog.tif",
        },
        "geometry": line_geometry(segments),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a GeoJSON catalog containing multiple SWOT pass tracks."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more SWOT NetCDF files. Shell wildcards are supported.",
    )
    parser.add_argument(
        "--output",
        default="frontend/public/data/swot_full_tracks.geojson",
        help="Output catalog GeoJSON path.",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=10,
        help="Keep every Nth along-track row for the lightweight overview line.",
    )
    parser.add_argument(
        "--browser-data-prefix",
        default="/data",
        help="Browser URL prefix used for companion nadir and COG files.",
    )
    parser.add_argument(
        "--variable",
        default="ssha_unfiltered",
        help="Variable name included in companion COG filenames.",
    )
    args = parser.parse_args()

    if args.stride < 1:
        raise ValueError("--stride must be at least 1.")

    input_paths = sorted(
        {Path(value).expanduser().resolve() for value in args.files}
    )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    features: list[dict[str, Any]] = []

    for index, nc_path in enumerate(input_paths, start=1):
        if not nc_path.exists():
            print(f"Skipping missing file: {nc_path}")
            continue

        print(f"[{index}/{len(input_paths)}] Reading {nc_path.name}")
        with xr.open_dataset(
            nc_path,
            mask_and_scale=True,
            decode_times=False,
        ) as ds:
            features.append(
                build_feature(
                    nc_path=nc_path,
                    ds=ds,
                    stride=args.stride,
                    browser_data_prefix=args.browser_data_prefix,
                    variable=args.variable,
                )
            )

    if not features:
        raise ValueError("No valid SWOT pass features were created.")

    catalog = {
        "type": "FeatureCollection",
        "properties": {
            "name": "SWOT Full Pass Track Catalog",
            "feature_count": len(features),
            "overview_stride": args.stride,
        },
        "features": features,
    }

    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(catalog, output_file, indent=2)

    print(f"Saved {len(features)} pass tracks to: {output_path}")


if __name__ == "__main__":
    main()
