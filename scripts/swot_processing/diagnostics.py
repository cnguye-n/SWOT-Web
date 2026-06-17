"""Create simple PNG previews and a JSON processing report.

The PNGs are diagnostic files only.

They do not affect the COG or GeoJSON outputs.
IT CREATES 
01_native_swath.png
02_resampled_raster.png
03_raster_with_nadir.png
report.json
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .data_models import (
    NadirTrack,
    RasterResult,
    SwotPassData,
)
from .nadir import split_nadir_segments


def save_native_preview(
    output_path: Path,
    swot_pass: SwotPassData,
    valid_mask: np.ndarray,
    display_min: float = -0.2,
    display_max: float = 0.2,
) -> None:
    """Save the valid native swath before resampling."""

    plotted_values = np.where(
        valid_mask,
        swot_pass.values,
        np.nan,
    )

    figure, axis = plt.subplots(
        figsize=(7, 9),
        dpi=150,
    )

    image = axis.pcolormesh(
        swot_pass.longitude,
        swot_pass.latitude,
        plotted_values,
        cmap="RdBu_r",
        vmin=display_min,
        vmax=display_max,
        shading="auto",
        rasterized=True,
    )

    axis.set_title("Native SWOT swath")
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")

    figure.colorbar(
        image,
        ax=axis,
        label=(
            f"{swot_pass.variable_name} "
            f"({swot_pass.units})"
        ),
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    figure.savefig(
        output_path,
        bbox_inches="tight",
        facecolor="white",
    )

    plt.close(figure)

    print(f"Saved diagnostic: {output_path}")


def save_resampled_preview(
    output_path: Path,
    swot_pass: SwotPassData,
    raster_result: RasterResult,
    nadir_track: NadirTrack | None = None,
    display_min: float = -0.2,
    display_max: float = 0.2,
) -> None:
    """Save the resampled raster, optionally with the nadir line."""

    west, south, east, north = (
        raster_result.bbox
    )

    figure, axis = plt.subplots(
        figsize=(7, 9),
        dpi=150,
    )

    image = axis.imshow(
        raster_result.data,
        extent=(
            west,
            east,
            south,
            north,
        ),
        origin="upper",
        cmap="RdBu_r",
        vmin=display_min,
        vmax=display_max,
        interpolation="nearest",
        aspect="auto",
    )

    if nadir_track is not None:
        segments = split_nadir_segments(
            nadir_track
        )

        for segment in segments:
            coordinates = np.asarray(segment)

            axis.plot(
                coordinates[:, 0],
                coordinates[:, 1],
                color="white",
                linewidth=3,
            )

            axis.plot(
                coordinates[:, 0],
                coordinates[:, 1],
                color="black",
                linewidth=1,
                linestyle="--",
            )

    axis.set_title(
        "Nearest-neighbor raster"
        + (
            " with nadir"
            if nadir_track is not None
            else ""
        )
    )

    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")

    figure.colorbar(
        image,
        ax=axis,
        label=(
            f"{swot_pass.variable_name} "
            f"({swot_pass.units})"
        ),
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    figure.savefig(
        output_path,
        bbox_inches="tight",
        facecolor="white",
    )

    plt.close(figure)

    print(f"Saved diagnostic: {output_path}")


def write_report(
    output_path: Path,
    report: dict,
) -> None:
    """Write processing information as readable JSON."""

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Saved report: {output_path}")