#!/usr/bin/env python3
"""Process one local SWOT NetCDF pass into web-ready map products.

Outputs:
- COG raster in frontend/public/data
- Nadir GeoJSON in frontend/public/data
- Diagnostic PNGs and report in outputs/diagnostics

The raster uses Pyresample nearest-neighbor resampling.
"""

import argparse
import re
from pathlib import Path

import numpy as np

from swot_processing.dataset import load_swot_pass
from swot_processing.diagnostics import (
    save_native_preview,
    save_resampled_preview,
    write_report,
)
from swot_processing.nadir import (
    extract_nadir_track,
    write_nadir_geojson,
)
from swot_processing.quality_masking import (
    apply_geographic_mask,
    build_quality_mask,
    derive_bbox,
    normalize_bbox,
    parse_quality_values,
)
from swot_processing.raster import (
    resample_nearest,
    write_cog,
)


def parse_arguments() -> argparse.Namespace:
    """Define the command-line options."""

    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input SWOT NetCDF file.",
    )

    parser.add_argument(
        "--variable",
        default="ssha_unfiltered",
        help=(
            "NetCDF variable to process. "
            "Default: ssha_unfiltered"
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("frontend/public/data"),
        help=(
            "Folder for the COG and nadir GeoJSON. "
            "Default: frontend/public/data"
        ),
    )

    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        default=Path("outputs/diagnostics"),
        help=(
            "Folder for diagnostic PNGs and report.json. "
            "Default: outputs/diagnostics"
        ),
    )

    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=(
            "WEST",
            "SOUTH",
            "EAST",
            "NORTH",
        ),
        help=(
            "Optional geographic bounding box. "
            "Example: --bbox -82 23 -69 42"
        ),
    )

    parser.add_argument(
        "--resolution-deg",
        type=float,
        default=0.0025,
        help=(
            "Output raster grid spacing in degrees. "
            "Default: 0.0025"
        ),
    )

    parser.add_argument(
        "--radius-m",
        type=float,
        default=None,
        help=(
            "Optional Pyresample search radius in meters. "
            "When omitted, the radius is estimated from "
            "the native SWOT spacing."
        ),
    )

    parser.add_argument(
        "--quality-values",
        type=parse_quality_values,
        default=(0, 3),
        help=(
            "Accepted quality flags as comma-separated values. "
            "Default: 0,3"
        ),
    )

    parser.add_argument(
        "--display-min",
        type=float,
        default=-0.2,
        help=(
            "Minimum SSHA value shown in diagnostic PNGs. "
            "Default: -0.2"
        ),
    )

    parser.add_argument(
        "--display-max",
        type=float,
        default=0.2,
        help=(
            "Maximum SSHA value shown in diagnostic PNGs. "
            "Default: 0.2"
        ),
    )

    parser.add_argument(
        "--nadir-max-gap-km",
        type=float,
        default=25.0,
        help=(
            "Split the nadir line when consecutive points "
            "are farther apart than this distance. "
            "Default: 25 km"
        ),
    )

    return parser.parse_args()


def create_output_prefix(source_path: Path) -> str:
    """Create a readable output name from cycle and pass numbers.

    Example input filename section:

        ..._014_091_20240420T163005_...

    Output:

        swot_cycle_014_pass_091
    """

    match = re.search(
        r"_(\d{3})_(\d{3})_\d{8}T",
        source_path.name,
    )

    if match is None:
        # Use the original filename when cycle and pass cannot be parsed.
        return source_path.stem

    cycle = match.group(1)
    pass_number = match.group(2)

    return f"swot_cycle_{cycle}_pass_{pass_number}"


def main() -> None:
    """Run the complete processing workflow for one SWOT pass."""

    arguments = parse_arguments()

    # Convert paths to absolute paths.
    input_path = arguments.input.expanduser().resolve()

    output_directory = (
        arguments.output_dir
        .expanduser()
        .resolve()
    )

    diagnostics_root = (
        arguments.diagnostics_dir
        .expanduser()
        .resolve()
    )

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input NetCDF file not found: {input_path}"
        )

    if arguments.display_min >= arguments.display_max:
        raise ValueError(
            "--display-min must be less than --display-max."
        )

    # Create the output folders when they do not exist.
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    diagnostics_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_prefix = create_output_prefix(
        input_path
    )

    # Web-ready outputs used by React.
    cog_path = (
        output_directory
        / (
            f"{output_prefix}_"
            f"{arguments.variable}_cog.tif"
        )
    )

    nadir_path = (
        output_directory
        / f"{output_prefix}_nadir.geojson"
    )

    # Diagnostic files are stored outside frontend/public.
    diagnostics_directory = (
        diagnostics_root
        / output_prefix
    )

    diagnostics_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    native_preview_path = (
        diagnostics_directory
        / "01_native_swath.png"
    )

    raster_preview_path = (
        diagnostics_directory
        / "02_resampled_raster.png"
    )

    combined_preview_path = (
        diagnostics_directory
        / "03_raster_with_nadir.png"
    )

    report_path = (
        diagnostics_directory
        / "report.json"
    )

    # --------------------------------------------------------------
    # 1. Load the local NetCDF file
    # --------------------------------------------------------------
    print("\n[1/5] Loading the SWOT NetCDF")

    swot_pass = load_swot_pass(
        source_path=input_path,
        variable_name=arguments.variable,
    )

    # --------------------------------------------------------------
    # 2. Build the quality and geographic masks
    # --------------------------------------------------------------
    print("\n[2/5] Applying quality and geographic masking")

    quality_mask = build_quality_mask(
        swot_pass=swot_pass,
        accepted_quality_flags=(
            arguments.quality_values
        ),
    )

    # Use the user-provided bbox when available.
    # Otherwise, derive bounds around valid native measurements.
    if arguments.bbox:
        bbox = normalize_bbox(
            arguments.bbox
        )
    else:
        bbox = derive_bbox(
            swot_pass=swot_pass,
            quality_mask=quality_mask,
        )

    final_mask = apply_geographic_mask(
        swot_pass=swot_pass,
        quality_mask=quality_mask,
        bbox=bbox,
    )

    # --------------------------------------------------------------
    # 3. Resample the valid swath and write the COG
    # --------------------------------------------------------------
    print("\n[3/5] Creating the nearest-neighbor COG")

    raster_result = resample_nearest(
        swot_pass=swot_pass,
        valid_mask=final_mask,
        bbox=bbox,
        resolution_deg=(
            arguments.resolution_deg
        ),
        radius_m=arguments.radius_m,
    )

    write_cog(
        output_path=cog_path,
        swot_pass=swot_pass,
        raster_result=raster_result,
        accepted_quality_flags=(
            arguments.quality_values
        ),
    )

    # --------------------------------------------------------------
    # 4. Create the separate nadir GeoJSON
    # --------------------------------------------------------------
    print("\n[4/5] Creating the nadir GeoJSON")

    nadir_track = extract_nadir_track(
        swot_pass=swot_pass,
        bbox=bbox,
        accepted_quality_flags=(
            arguments.quality_values
        ),
    )

    nadir_report = write_nadir_geojson(
        output_path=nadir_path,
        swot_pass=swot_pass,
        nadir_track=nadir_track,
        max_gap_km=(
            arguments.nadir_max_gap_km
        ),
    )

    # --------------------------------------------------------------
    # 5. Create diagnostic PNGs and the JSON report
    # --------------------------------------------------------------
    print("\n[5/5] Creating diagnostic files")

    save_native_preview(
        output_path=native_preview_path,
        swot_pass=swot_pass,
        valid_mask=final_mask,
        nadir_track=nadir_track,
        display_min=arguments.display_min,
        display_max=arguments.display_max,
    )

    save_resampled_preview(
        output_path=raster_preview_path,
        swot_pass=swot_pass,
        raster_result=raster_result,
        display_min=arguments.display_min,
        display_max=arguments.display_max,
    )

    save_resampled_preview(
        output_path=combined_preview_path,
        swot_pass=swot_pass,
        raster_result=raster_result,
        nadir_track=nadir_track,
        display_min=arguments.display_min,
        display_max=arguments.display_max,
    )

    report = {
        "input_file": str(input_path),
        "variable": swot_pass.variable_name,
        "units": swot_pass.units,
        "native_shape": list(
            swot_pass.values.shape
        ),
        "bbox": list(bbox),
        "accepted_quality_flags": list(
            arguments.quality_values
        ),
        "quality_valid_cells": int(
            quality_mask.sum()
        ),
        "regional_valid_cells": int(
            final_mask.sum()
        ),
        "output_width": (
            raster_result.width
        ),
        "output_height": (
            raster_result.height
        ),
        "output_resolution_deg": (
            raster_result.resolution_deg
        ),
        "estimated_source_spacing_m": (
            raster_result.source_spacing_m
        ),
        "radius_of_influence_m": (
            raster_result.radius_m
        ),
        "finite_output_cells": int(
            np.count_nonzero(
                np.isfinite(
                    raster_result.data
                )
            )
        ),
        "cog_path": str(cog_path),
        "nadir": nadir_report,
        "diagnostics": {
            "native_swath_png": str(
                native_preview_path
            ),
            "resampled_raster_png": str(
                raster_preview_path
            ),
            "raster_with_nadir_png": str(
                combined_preview_path
            ),
        },
    }

    write_report(
        output_path=report_path,
        report=report,
    )

    print("\nProcessing complete")
    print(f"COG:         {cog_path}")
    print(f"Nadir:       {nadir_path}")
    print(f"Diagnostics: {diagnostics_directory}")


if __name__ == "__main__":
    main()