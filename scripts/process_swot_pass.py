#!/usr/bin/env python3
""" Controller that calls all the other files
Process one local SWOT pass into web-ready map products."""

import argparse
import re
from pathlib import Path

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
        help="Input SWOT NetCDF file.",
    )

    parser.add_argument(
        "--variable",
        default="ssha_unfiltered",
        help="Variable to process.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("frontend/public/data"),
        help="Output directory.",
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
        help="Optional regional bounding box.",
    )

    parser.add_argument(
        "--resolution-deg",
        type=float,
        default=0.0025,
        help="Output grid spacing in degrees.",
    )

    parser.add_argument(
        "--radius-m",
        type=float,
        default=None,
        help="Optional Pyresample search radius.",
    )

    parser.add_argument(
        "--quality-values",
        type=parse_quality_values,
        default=(0, 3),
        help="Accepted quality flags. Default: 0,3",
    )

    parser.add_argument(
        "--display-min",
        type=float,
        default=-0.2,
        help="Minimum diagnostic display value.",
    )

    parser.add_argument(
        "--display-max",
        type=float,
        default=0.2,
        help="Maximum diagnostic display value.",
    )

    return parser.parse_args()


def create_output_prefix(
    source_path: Path,
) -> str:
    """Create a short output name using cycle and pass."""

    match = re.search(
        r"_(\d{3})_(\d{3})_\d{8}T",
        source_path.name,
    )

    if match is None:
        return source_path.stem

    cycle = match.group(1)
    pass_number = match.group(2)

    return (
        f"swot_cycle_{cycle}"
        f"_pass_{pass_number}"
    )


def main() -> None:
    """Run the complete processing workflow."""

    arguments = parse_arguments()

    input_path = (
        arguments.input
        .expanduser()
        .resolve()
    )

    output_directory = (
        arguments.output_dir
        .expanduser()
        .resolve()
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_prefix = create_output_prefix(
        input_path
    )

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

    diagnostics_directory = (
        output_directory
        / "diagnostics"
        / output_prefix
    )

    print("\n1. Load the local NetCDF")

    swot_pass = load_swot_pass(
        source_path=input_path,
        variable_name=arguments.variable,
    )

    print("\n2. Create the quality mask")

    quality_mask = build_quality_mask(
        swot_pass=swot_pass,
        accepted_quality_flags=(
            arguments.quality_values
        ),
    )

    # Use the requested bbox when provided.
    # Otherwise, create bounds around the valid measurements.
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

    print("\n3. Create the nearest-neighbor raster")

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

    print("\n4. Create the separate nadir GeoJSON")

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
    )

    print("\n5. Create diagnostic files")

    save_native_preview(
        output_path=(
            diagnostics_directory
            / "01_native_swath.png"
        ),
        swot_pass=swot_pass,
        valid_mask=final_mask,
        display_min=arguments.display_min,
        display_max=arguments.display_max,
    )

    save_resampled_preview(
        output_path=(
            diagnostics_directory
            / "02_resampled_raster.png"
        ),
        swot_pass=swot_pass,
        raster_result=raster_result,
        display_min=arguments.display_min,
        display_max=arguments.display_max,
    )

    save_resampled_preview(
        output_path=(
            diagnostics_directory
            / "03_raster_with_nadir.png"
        ),
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
        "bbox": list(bbox),
        "accepted_quality_flags": list(
            arguments.quality_values
        ),
        "native_shape": list(
            swot_pass.values.shape
        ),
        "quality_valid_cells": int(
            quality_mask.sum()
        ),
        "regional_valid_cells": int(
            final_mask.sum()
        ),
        "output_width": raster_result.width,
        "output_height": raster_result.height,
        "output_resolution_deg": (
            raster_result.resolution_deg
        ),
        "source_spacing_m": (
            raster_result.source_spacing_m
        ),
        "radius_m": raster_result.radius_m,
        "finite_output_cells": int(
            (
                raster_result.data
                == raster_result.data
            ).sum()
        ),
        "cog_path": str(cog_path),
        "nadir": nadir_report,
    }

    write_report(
        output_path=(
            diagnostics_directory
            / "report.json"
        ),
        report=report,
    )

    print("\nProcessing complete")
    print(f"COG:   {cog_path}")
    print(f"Nadir: {nadir_path}")
    print(
        "Diagnostics: "
        f"{diagnostics_directory}"
    )


if __name__ == "__main__":
    main()