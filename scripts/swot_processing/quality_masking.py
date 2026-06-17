"""Quality-control and geographic masks for SWOT swath data.

This module does not modify, crop, or resample the SWOT arrays.

Instead, it creates Boolean arrays with the same shape as the native
SWOT longitude, latitude, and SSHA arrays:

    True  -> keep this native SWOT measurement
    False -> exclude this native SWOT measurement

The final mask is later passed to raster.py. Raster processing uses only
the cells marked True when performing Pyresample nearest-neighbor
resampling.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable

import numpy as np

from .data_models import BoundingBox, SwotPassData


# Default L3 quality flags accepted by this visualization workflow.
#
# 0 = valid measurement
# 3 = eclipse-related flag
#
# Use (0,) instead when only fully valid measurements should be kept.
DEFAULT_QUALITY_FLAGS = (0, 3)


def parse_quality_values(text: str) -> tuple[int, ...]:
    """Convert a command-line string such as '0,3' into integers.

    Example:
        "0,3" -> (0, 3)

    This function is only needed so the command line can support:

        --quality-values 0,3
    """

    try:
        values = tuple(
            sorted(
                {
                    int(item.strip())
                    for item in text.split(",")
                    if item.strip()
                }
            )
        )

    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Quality values must be comma-separated integers, "
            "such as 0,3."
        ) from error

    if not values:
        raise argparse.ArgumentTypeError(
            "At least one quality value is required."
        )

    return values


def normalize_bbox(
    bbox: Iterable[float],
) -> BoundingBox:
    """Validate a geographic bounding box.

    The expected order is:

        west, south, east, north

    Example for the Gulf Stream:

        (-82, 23, -69, 42)
    """

    west, south, east, north = map(float, bbox)

    # Make sure the longitude bounds are valid and ordered correctly.
    if not -180.0 <= west < east <= 180.0:
        raise ValueError(
            "Longitude bounds must satisfy "
            "-180 <= west < east <= 180."
        )

    # Make sure the latitude bounds are valid and ordered correctly.
    if not -90.0 <= south < north <= 90.0:
        raise ValueError(
            "Latitude bounds must satisfy "
            "-90 <= south < north <= 90."
        )

    return west, south, east, north


def build_quality_mask(
    swot_pass: SwotPassData,
    accepted_quality_flags: tuple[int, ...] = DEFAULT_QUALITY_FLAGS,
) -> np.ndarray:
    """Select native cells that pass basic and product quality control.

    A cell is kept only when:

    1. longitude is finite;
    2. latitude is finite;
    3. the requested SSHA value is finite;
    4. latitude is physically valid;
    5. quality_flag is one of the accepted values.

    This function does not yet apply the geographic bounding box.
    """

    # Start with basic coordinate and value validity.
    #
    # np.isfinite() rejects:
    # - NaN
    # - positive infinity
    # - negative infinity
    #
    # These values must not be passed into Pyresample.
    finite_measurements = (
        np.isfinite(swot_pass.longitude)
        & np.isfinite(swot_pass.latitude)
        & np.isfinite(swot_pass.values)
        & (swot_pass.latitude >= -90.0)
        & (swot_pass.latitude <= 90.0)
    )

    # Our land and product-quality filtering depends on quality_flag.
    # Failing clearly is safer than silently processing unfiltered land.
    if swot_pass.quality_flag is None:
        raise ValueError(
            "This NetCDF file does not contain quality_flag. "
            "The requested ocean-quality mask cannot be applied."
        )

    # The quality array must describe the same native grid as SSHA.
    if swot_pass.quality_flag.shape != swot_pass.values.shape:
        raise ValueError(
            "quality_flag does not have the same shape as the "
            "longitude, latitude, and SSHA arrays."
        )

    # Keep only explicitly accepted SWOT quality values.
    #
    # With accepted_quality_flags=(0, 3):
    #
    # flag 0   -> True
    # flag 3   -> True
    # flag 101 -> False, so product-identified land is excluded
    # flag 102 -> False, so missing data is excluded
    # all other values -> False
    accepted_product_quality = np.isin(
        swot_pass.quality_flag,
        accepted_quality_flags,
    )

    # A cell must pass both basic checks and the product quality flag.
    quality_mask = (
        finite_measurements
        & accepted_product_quality
    )

    print("Quality masking")
    print(
        "  Accepted quality flags:",
        accepted_quality_flags,
    )
    print(
        "  Finite native cells:",
        f"{int(finite_measurements.sum()):,}",
    )
    print(
        "  Cells after quality filtering:",
        f"{int(quality_mask.sum()):,}",
    )

    return quality_mask


def derive_bbox(
    swot_pass: SwotPassData,
    quality_mask: np.ndarray,
    padding_deg: float = 0.05,
) -> BoundingBox:
    """Create bounds around all measurements that passed quality control.

    This is used only when the user does not provide an explicit --bbox.

    A small amount of padding is added around the outer valid cells.
    """

    valid_longitude = swot_pass.longitude[
        quality_mask
    ]

    valid_latitude = swot_pass.latitude[
        quality_mask
    ]

    if valid_longitude.size == 0:
        raise ValueError(
            "No valid measurements remain after quality masking."
        )

    # A simple longitude minimum and maximum do not work correctly
    # when a satellite pass crosses the ±180-degree antimeridian.
    if (
        np.nanmax(valid_longitude)
        - np.nanmin(valid_longitude)
        > 180.0
    ):
        raise ValueError(
            "The pass crosses the antimeridian. "
            "Provide an explicit regional --bbox."
        )

    west = max(
        -180.0,
        float(np.nanmin(valid_longitude))
        - padding_deg,
    )

    east = min(
        180.0,
        float(np.nanmax(valid_longitude))
        + padding_deg,
    )

    south = max(
        -90.0,
        float(np.nanmin(valid_latitude))
        - padding_deg,
    )

    north = min(
        90.0,
        float(np.nanmax(valid_latitude))
        + padding_deg,
    )

    return west, south, east, north


def apply_geographic_mask(
    swot_pass: SwotPassData,
    quality_mask: np.ndarray,
    bbox: BoundingBox,
) -> np.ndarray:
    """Keep quality-controlled cells inside the requested region.

    The original array shape is preserved.

    Measurements outside the bounding box become False rather than
    being deleted or rearranged.
    """

    west, south, east, north = bbox

    # Check whether every native measurement lies inside the AOI.
    inside_bbox = (
        (swot_pass.longitude >= west)
        & (swot_pass.longitude <= east)
        & (swot_pass.latitude >= south)
        & (swot_pass.latitude <= north)
    )

    # A cell must:
    #
    # 1. pass quality control, and
    # 2. be located inside the requested geographic region.
    final_mask = (
        quality_mask
        & inside_bbox
    )

    if not np.any(final_mask):
        raise ValueError(
            "No accepted SWOT measurements intersect the "
            "selected bounding box."
        )

    print("Geographic masking")
    print(f"  Bounding box: {bbox}")
    print(
        "  Final native cells:",
        f"{int(final_mask.sum()):,}",
    )

    return final_mask


def build_final_mask(
    swot_pass: SwotPassData,
    bbox: BoundingBox,
    accepted_quality_flags: tuple[int, ...] = DEFAULT_QUALITY_FLAGS,
) -> np.ndarray:
    """Create the complete mask used by raster processing.

    This convenience function applies both steps:

        SWOT product quality control
                    +
        geographic bounding-box filtering
                    =
        final Boolean raster-source mask
    """

    quality_mask = build_quality_mask(
        swot_pass=swot_pass,
        accepted_quality_flags=accepted_quality_flags,
    )

    final_mask = apply_geographic_mask(
        swot_pass=swot_pass,
        quality_mask=quality_mask,
        bbox=bbox,
    )

    return final_mask