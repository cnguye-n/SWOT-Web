"""Create a separate GeoJSON layer for SWOT nadir observations.

The nadir is not written into the COG.

The file uses i_num_line and i_num_pixel to map each original nadir
observation back onto the two-dimensional L3 grid.
"""

import json
import re
from pathlib import Path

import numpy as np

from .data_models import (
    BoundingBox,
    NadirTrack,
    SwotPassData,
)
from .raster import haversine_m


def extract_nadir_track(
    swot_pass: SwotPassData,
    bbox: BoundingBox,
    accepted_quality_flags: tuple[int, ...] = (0, 3),
) -> NadirTrack:
    """Map the nadir observations and apply only finite + bbox filtering.

    Important:
    Do NOT apply the KaRIn quality_flag to the mapped nadir line.

    In SWOT L3 Expert/Basic, the nadir observations are mapped back
    into the 2-D image using i_num_line and i_num_pixel. Those mapped
    cells can sit in the center-gap / KaRIn no-data area, so the KaRIn
    quality_flag can say the cell is invalid even when the nadir point
    itself is real.

    accepted_quality_flags is kept in the function signature so
    process_swot_pass.py does not need to change, but it is not used
    for nadir filtering.
    """

    if (
        swot_pass.i_num_line is None
        or swot_pass.i_num_pixel is None
    ):
        raise ValueError(
            "This NetCDF does not contain i_num_line and i_num_pixel."
        )

    source_lines = np.asarray(
        swot_pass.i_num_line,
        dtype=np.int64,
    )

    source_pixels = np.asarray(
        swot_pass.i_num_pixel,
        dtype=np.int64,
    )

    if source_lines.shape != source_pixels.shape:
        raise ValueError(
            "i_num_line and i_num_pixel have different shapes."
        )

    longitude = np.full(
        source_lines.shape,
        np.nan,
        dtype=np.float64,
    )

    latitude = np.full(
        source_lines.shape,
        np.nan,
        dtype=np.float64,
    )

    values = np.full(
        source_lines.shape,
        np.nan,
        dtype=np.float64,
    )

    valid_indices = (
        (source_lines >= 0)
        & (source_lines < swot_pass.longitude.shape[0])
        & (source_pixels >= 0)
        & (source_pixels < swot_pass.longitude.shape[1])
    )

    longitude[valid_indices] = swot_pass.longitude[
        source_lines[valid_indices],
        source_pixels[valid_indices],
    ]

    latitude[valid_indices] = swot_pass.latitude[
        source_lines[valid_indices],
        source_pixels[valid_indices],
    ]

    values[valid_indices] = swot_pass.values[
        source_lines[valid_indices],
        source_pixels[valid_indices],
    ]

    west, south, east, north = bbox

    keep = (
        np.isfinite(longitude)
        & np.isfinite(latitude)
        & np.isfinite(values)
        & (longitude >= west)
        & (longitude <= east)
        & (latitude >= south)
        & (latitude <= north)
    )

    longitude[~keep] = np.nan
    latitude[~keep] = np.nan
    values[~keep] = np.nan

    print(
        "Valid nadir observations: "
        f"{int(np.count_nonzero(keep)):,}"
    )

    return NadirTrack(
        longitude=longitude,
        latitude=latitude,
        values=values,
    )


def split_nadir_segments(
    nadir_track: NadirTrack,
    max_gap_km: float = 25.0,
) -> list[list[list[float]]]:
    """Split the nadir track at missing points or large gaps."""

    segments: list[list[list[float]]] = []
    current_segment: list[list[float]] = []

    previous_index: int | None = None

    for index in range(
        nadir_track.longitude.size
    ):
        longitude = nadir_track.longitude[index]
        latitude = nadir_track.latitude[index]

        point_is_valid = (
            np.isfinite(longitude)
            and np.isfinite(latitude)
        )

        if not point_is_valid:
            if len(current_segment) >= 2:
                segments.append(current_segment)

            current_segment = []
            previous_index = None
            continue

        if previous_index is not None:
            distance_m = float(
                haversine_m(
                    np.array(
                        [
                            nadir_track.longitude[
                                previous_index
                            ]
                        ]
                    ),
                    np.array(
                        [
                            nadir_track.latitude[
                                previous_index
                            ]
                        ]
                    ),
                    np.array([longitude]),
                    np.array([latitude]),
                )[0]
            )

            # Start a new segment rather than connecting points
            # separated by an unrealistic distance.
            if distance_m > max_gap_km * 1000.0:
                if len(current_segment) >= 2:
                    segments.append(
                        current_segment
                    )

                current_segment = []

        current_segment.append(
            [
                float(longitude),
                float(latitude),
            ]
        )

        previous_index = index

    if len(current_segment) >= 2:
        segments.append(current_segment)

    return segments


def parse_cycle_and_pass(
    source_path: Path,
) -> tuple[str | None, str | None]:
    """Extract cycle and pass numbers from a SWOT filename."""

    match = re.search(
        r"_(\d{3})_(\d{3})_\d{8}T",
        source_path.name,
    )

    if match is None:
        return None, None

    return match.group(1), match.group(2)


def write_nadir_geojson(
    output_path: Path,
    swot_pass: SwotPassData,
    nadir_track: NadirTrack,
    max_gap_km: float = 25.0,
) -> dict:
    """Write every valid nadir segment as a GeoJSON LineString."""

    segments = split_nadir_segments(
        nadir_track,
        max_gap_km=max_gap_km,
    )

    if not segments:
        raise ValueError(
            "No valid nadir line segments remain."
        )

    cycle, pass_number = parse_cycle_and_pass(
        swot_pass.source_path
    )

    features = []

    for segment_number, coordinates in enumerate(
        segments,
        start=1,
    ):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": "SWOT nadir track",
                    "cycle": cycle,
                    "pass": pass_number,
                    "segment": segment_number,
                    "source_file": (
                        swot_pass.source_path.name
                    ),
                    "variable": (
                        swot_pass.variable_name
                    ),
                    "point_count": len(coordinates),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    output_path = output_path.expanduser().resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            geojson,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = {
        "path": str(output_path),
        "segment_count": len(segments),
        "point_count": sum(
            len(segment)
            for segment in segments
        ),
    }

    print(f"Saved nadir GeoJSON: {output_path}")

    return report