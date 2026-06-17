"""Create a Cloud Optimized GeoTIFF from a SWOT swath.
IT CREATES THE GOG.TIFF and only the source cells where the final mask is True are passed into Pyresample
Processing steps:

    valid native SWOT measurements
                ↓
    Pyresample nearest-neighbor resampling
                ↓
    temporary GeoTIFF
                ↓
    Cloud Optimized GeoTIFF

Nearest-neighbor resampling copies existing source values.
It does not blend neighboring SSHA measurements.
"""

import math
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from pyresample import geometry, kd_tree
from rasterio.enums import Resampling
from rasterio.shutil import copy as rasterio_copy
from rasterio.transform import from_bounds

from .data_models import (
    BoundingBox,
    RasterResult,
    SwotPassData,
)


EARTH_RADIUS_M = 6_371_008.8
DEFAULT_NODATA = -9999.0


def haversine_m(
    lon1: np.ndarray,
    lat1: np.ndarray,
    lon2: np.ndarray,
    lat2: np.ndarray,
) -> np.ndarray:
    """Calculate great-circle distance in meters."""

    lon1_rad = np.deg2rad(lon1)
    lat1_rad = np.deg2rad(lat1)
    lon2_rad = np.deg2rad(lon2)
    lat2_rad = np.deg2rad(lat2)

    delta_lon = lon2_rad - lon1_rad
    delta_lat = lat2_rad - lat1_rad

    a = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat1_rad)
        * np.cos(lat2_rad)
        * np.sin(delta_lon / 2.0) ** 2
    )

    return (
        2.0
        * EARTH_RADIUS_M
        * np.arcsin(
            np.minimum(1.0, np.sqrt(a))
        )
    )


def estimate_source_spacing_m(
    swot_pass: SwotPassData,
    valid_mask: np.ndarray,
) -> float:
    """Estimate the typical spacing between native SWOT cells.

    The function checks both:

    - neighboring along-track cells;
    - neighboring across-track cells.

    Very large distances, such as the nadir gap, are removed before
    calculating the representative median spacing.
    """

    distance_groups: list[np.ndarray] = []

    neighbor_pairs = [
        # Along-track neighbors.
        (
            (slice(None, -1), slice(None)),
            (slice(1, None), slice(None)),
        ),

        # Across-track neighbors.
        (
            (slice(None), slice(None, -1)),
            (slice(None), slice(1, None)),
        ),
    ]

    for first, second in neighbor_pairs:
        pair_is_valid = (
            valid_mask[first]
            & valid_mask[second]
        )

        if not np.any(pair_is_valid):
            continue

        distances = haversine_m(
            swot_pass.longitude[first][pair_is_valid],
            swot_pass.latitude[first][pair_is_valid],
            swot_pass.longitude[second][pair_is_valid],
            swot_pass.latitude[second][pair_is_valid],
        )

        distance_groups.append(distances)

    if not distance_groups:
        raise ValueError(
            "Could not estimate native SWOT spacing."
        )

    distances = np.concatenate(distance_groups)

    distances = distances[
        np.isfinite(distances)
        & (distances > 0.0)
    ]

    if distances.size == 0:
        raise ValueError(
            "No usable neighboring cell distances were found."
        )

    # Remove the largest distances, which may include the nadir gap
    # or gaps caused by missing measurements.
    upper_limit = np.nanpercentile(
        distances,
        75,
    )

    typical_distances = distances[
        distances <= upper_limit
    ]

    source_spacing_m = float(
        np.nanmedian(typical_distances)
    )

    print(
        "Estimated native spacing: "
        f"{source_spacing_m:,.1f} meters"
    )

    return source_spacing_m


def create_target_area(
    bbox: BoundingBox,
    resolution_deg: float,
) -> tuple[geometry.AreaDefinition, int, int]:
    """Create a regular latitude/longitude output grid."""

    if resolution_deg <= 0.0:
        raise ValueError(
            "resolution_deg must be greater than zero."
        )

    west, south, east, north = bbox

    width = max(
        1,
        math.ceil(
            (east - west) / resolution_deg
        ),
    )

    height = max(
        1,
        math.ceil(
            (north - south) / resolution_deg
        ),
    )

    # Prevent accidentally creating an extremely large output.
    cell_count = width * height

    if cell_count > 50_000_000:
        raise ValueError(
            "The requested raster is too large.\n"
            f"Requested size: {width:,} x {height:,}\n"
            "Use a smaller bbox or a larger resolution."
        )

    target_area = geometry.AreaDefinition(
        area_id="swot_output",
        description="Regular SWOT output grid",
        proj_id="epsg4326",
        projection="EPSG:4326",
        width=width,
        height=height,
        area_extent=(
            west,
            south,
            east,
            north,
        ),
    )

    return target_area, width, height


def resample_nearest(
    swot_pass: SwotPassData,
    valid_mask: np.ndarray,
    bbox: BoundingBox,
    resolution_deg: float = 0.0025,
    radius_m: float | None = None,
) -> RasterResult:
    """Resample the valid native swath using nearest neighbour."""

    source_spacing_m = estimate_source_spacing_m(
        swot_pass,
        valid_mask,
    )

    # If no search radius is provided, use a radius slightly larger
    # than the estimated source spacing.
    #
    # A larger radius fills more output cells but may make the swath
    # look slightly wider at its edges.
    if radius_m is None:
        radius_m = source_spacing_m * 1.25

    if radius_m <= 0.0:
        raise ValueError(
            "radius_m must be greater than zero."
        )

    target_area, width, height = create_target_area(
        bbox=bbox,
        resolution_deg=resolution_deg,
    )

    # Select only measurements marked True by quality_masking.py.
    source_longitude = swot_pass.longitude[
        valid_mask
    ]

    source_latitude = swot_pass.latitude[
        valid_mask
    ]

    source_values = swot_pass.values[
        valid_mask
    ].astype(np.float32)

    source_swath = geometry.SwathDefinition(
        lons=source_longitude,
        lats=source_latitude,
    )

    print("Running Pyresample nearest neighbour")
    print(f"  Source cells: {source_values.size:,}")
    print(f"  Output size:  {width:,} x {height:,}")
    print(f"  Search radius: {radius_m:,.1f} meters")

    resampled_data = kd_tree.resample_nearest(
        source_geo_def=source_swath,
        data=source_values,
        target_geo_def=target_area,
        radius_of_influence=radius_m,
        epsilon=0.0,
        fill_value=np.nan,
        reduce_data=True,
    )

    raster_data = np.asarray(
        resampled_data,
        dtype=np.float32,
    )

    print(
        "Finite output cells: "
        f"{int(np.count_nonzero(np.isfinite(raster_data))):,}"
    )

    return RasterResult(
        data=raster_data,
        bbox=bbox,
        width=width,
        height=height,
        resolution_deg=resolution_deg,
        source_spacing_m=source_spacing_m,
        radius_m=float(radius_m),
        nodata=DEFAULT_NODATA,
    )


def write_cog(
    output_path: Path,
    swot_pass: SwotPassData,
    raster_result: RasterResult,
    accepted_quality_flags: tuple[int, ...],
) -> None:
    """Write the resampled data as a Cloud Optimized GeoTIFF."""

    output_path = output_path.expanduser().resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    west, south, east, north = (
        raster_result.bbox
    )

    transform = from_bounds(
        west,
        south,
        east,
        north,
        raster_result.width,
        raster_result.height,
    )

    # Replace NaN with the raster nodata value before writing.
    encoded_data = np.where(
        np.isfinite(raster_result.data),
        raster_result.data,
        raster_result.nodata,
    ).astype(np.float32)

    with tempfile.TemporaryDirectory(
        prefix="swot_cog_"
    ) as temporary_directory:

        temporary_tiff = (
            Path(temporary_directory)
            / "temporary.tif"
        )

        # First write a normal tiled GeoTIFF.
        with rasterio.open(
            temporary_tiff,
            "w",
            driver="GTiff",
            height=raster_result.height,
            width=raster_result.width,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=raster_result.nodata,
            tiled=True,
            blockxsize=512,
            blockysize=512,
            compress="DEFLATE",
            predictor=3,
            BIGTIFF="IF_SAFER",
        ) as destination:

            destination.write(
                encoded_data,
                1,
            )

            destination.set_band_description(
                1,
                swot_pass.variable_name,
            )

            destination.update_tags(
                source_file=swot_pass.source_path.name,
                source_variable=swot_pass.variable_name,
                source_units=swot_pass.units,
                processing_method="pyresample_nearest_neighbour",
                output_resolution_deg=str(
                    raster_result.resolution_deg
                ),
                estimated_source_spacing_m=str(
                    raster_result.source_spacing_m
                ),
                radius_of_influence_m=str(
                    raster_result.radius_m
                ),
                accepted_quality_flags=",".join(
                    map(
                        str,
                        accepted_quality_flags,
                    )
                ),
            )

        # Convert the temporary GeoTIFF into COG format.
        rasterio_copy(
            temporary_tiff,
            output_path,
            driver="COG",
            compress="DEFLATE",
            blocksize=512,
            overview_resampling=(
                Resampling.nearest.name
            ),
            BIGTIFF="IF_SAFER",
        )

    print(f"Saved COG: {output_path}")