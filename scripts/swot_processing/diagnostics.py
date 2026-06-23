"""Create simple PNG previews and a JSON processing report.

The PNGs are diagnostic files only.

They do not affect the COG or GeoJSON outputs.

This file creates:
- 01_native_swath.png
- 02_resampled_raster.png
- 03_raster_with_nadir.png
- report.json
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

# ------------------------------------------------------------
# Optional coastline support.
# If Cartopy is unavailable, the script still runs.
# ------------------------------------------------------------
try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    CARTOPY_AVAILABLE = True
except ImportError:
    ccrs = None
    cfeature = None
    CARTOPY_AVAILABLE = False


def create_map_figure():
    """Create either a Cartopy map axis or a normal matplotlib axis."""
    if CARTOPY_AVAILABLE:
        figure, axis = plt.subplots(
            figsize=(7, 9),
            dpi=150,
            subplot_kw={"projection": ccrs.PlateCarree()},
        )
    else:
        figure, axis = plt.subplots(
            figsize=(7, 9),
            dpi=150,
        )

    return figure, axis


def get_plot_transform():
    """Return the lon/lat transform when Cartopy is available."""
    if CARTOPY_AVAILABLE:
        return ccrs.PlateCarree()
    return None


def set_map_extent(
    axis,
    west: float,
    south: float,
    east: float,
    north: float,
) -> None:
    """Set plot extent for either Cartopy or normal matplotlib."""
    if CARTOPY_AVAILABLE:
        axis.set_extent(
            [west, east, south, north],
            crs=ccrs.PlateCarree(),
        )
    else:
        axis.set_xlim(west, east)
        axis.set_ylim(south, north)


def add_grid(axis) -> None:
    """Add light grid lines and coordinate labels."""
    if CARTOPY_AVAILABLE:
        gridliner = axis.gridlines(
            draw_labels=True,
            linewidth=0.4,
            color="0.85",
            alpha=0.8,
            linestyle="-",
        )
        gridliner.top_labels = False
        gridliner.right_labels = False
    else:
        axis.grid(
            color="0.85",
            linewidth=0.4,
            alpha=0.8,
        )


def add_coastline(axis) -> None:
    """Add land and coastline on top of the SSHA layer."""
    if not CARTOPY_AVAILABLE:
        print(
            "Cartopy is not installed, so coastline was skipped. "
            "Install cartopy if you want coastlines in diagnostic PNGs."
        )
        return

    axis.add_feature(
        cfeature.LAND.with_scale("10m"),
        facecolor="white",
        edgecolor="0.35",
        linewidth=0.7,
        zorder=6,
    )

    axis.coastlines(
        resolution="10m",
        color="0.35",
        linewidth=0.8,
        zorder=7,
    )


def add_colored_nadir_points(
    axis,
    nadir_track: NadirTrack,
    display_min: float,
    display_max: float,
) -> None:
    """Draw nadir as colored native measurement points."""

    longitude = np.asarray(
        nadir_track.longitude,
        dtype=np.float64,
    )
    latitude = np.asarray(
        nadir_track.latitude,
        dtype=np.float64,
    )
    values = np.asarray(
        nadir_track.values,
        dtype=np.float64,
    )

    valid = (
        np.isfinite(longitude)
        & np.isfinite(latitude)
        & np.isfinite(values)
    )

    if not np.any(valid):
        print("No valid nadir points to draw.")
        return

    plot_transform = get_plot_transform()
    scatter_kwargs = {}

    if plot_transform is not None:
        scatter_kwargs["transform"] = plot_transform

    # White backing dots so they remain visible over the swath.
    axis.scatter(
        longitude[valid],
        latitude[valid],
        s=14,
        c="white",
        linewidths=0,
        zorder=8,
        **scatter_kwargs,
    )

    # Colored native nadir measurements.
    axis.scatter(
        longitude[valid],
        latitude[valid],
        s=7,
        c=values[valid],
        cmap="RdBu_r",
        vmin=display_min,
        vmax=display_max,
        linewidths=0,
        zorder=9,
        **scatter_kwargs,
    )


def save_native_preview(
    output_path: Path,
    swot_pass: SwotPassData,
    valid_mask: np.ndarray,
    nadir_track: NadirTrack | None = None,
    display_min: float = -0.2,
    display_max: float = 0.2,
) -> None:
    """Save the valid native swath before resampling.

    This plots the original SWOT L3 swath grid directly.
    It zooms to the valid regional cells so the swath does not
    appear tiny on a full-pass/global axis.
    """

    plotted_values = np.where(
        valid_mask,
        swot_pass.values,
        np.nan,
    )

    figure, axis = create_map_figure()

    pcolormesh_kwargs = {}
    plot_transform = get_plot_transform()

    if plot_transform is not None:
        pcolormesh_kwargs["transform"] = plot_transform

    image = axis.pcolormesh(
        swot_pass.longitude,
        swot_pass.latitude,
        plotted_values,
        cmap="RdBu_r",
        vmin=display_min,
        vmax=display_max,
        shading="auto",
        rasterized=True,
        zorder=1,
        **pcolormesh_kwargs,
    )

    axis.set_title(
        "Native SWOT swath"
        + (
            " with native nadir points"
            if nadir_track is not None
            else ""
        )
    )
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")

    valid_longitude = swot_pass.longitude[valid_mask]
    valid_latitude = swot_pass.latitude[valid_mask]

    if valid_longitude.size > 0 and valid_latitude.size > 0:
        padding_deg = 0.15

        west = float(np.nanmin(valid_longitude)) - padding_deg
        east = float(np.nanmax(valid_longitude)) + padding_deg
        south = float(np.nanmin(valid_latitude)) - padding_deg
        north = float(np.nanmax(valid_latitude)) + padding_deg

        set_map_extent(
            axis=axis,
            west=west,
            south=south,
            east=east,
            north=north,
        )

    add_grid(axis)
    add_coastline(axis)

    if nadir_track is not None:
        add_colored_nadir_points(
            axis=axis,
            nadir_track=nadir_track,
            display_min=display_min,
            display_max=display_max,
        )

    figure.colorbar(
        image,
        ax=axis,
        label=f"{swot_pass.variable_name} ({swot_pass.units})",
        shrink=0.85,
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
    """Save the resampled raster, optionally with colored nadir points."""

    west, south, east, north = raster_result.bbox

    figure, axis = create_map_figure()

    imshow_kwargs = {}
    plot_transform = get_plot_transform()

    if plot_transform is not None:
        imshow_kwargs["transform"] = plot_transform

    image = axis.imshow(
        raster_result.data,
        extent=(west, east, south, north),
        origin="upper",
        cmap="RdBu_r",
        vmin=display_min,
        vmax=display_max,
        interpolation="nearest",
        zorder=1,
        **imshow_kwargs,
    )

    set_map_extent(
        axis=axis,
        west=west,
        south=south,
        east=east,
        north=north,
    )

    add_grid(axis)
    add_coastline(axis)

    if nadir_track is not None:
        add_colored_nadir_points(
            axis=axis,
            nadir_track=nadir_track,
            display_min=display_min,
            display_max=display_max,
        )

    axis.set_title(
        "Nearest-neighbor raster"
        + (
            " with native nadir points"
            if nadir_track is not None
            else ""
        )
    )

    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")

    figure.colorbar(
        image,
        ax=axis,
        label=f"{swot_pass.variable_name} ({swot_pass.units})",
        shrink=0.85,
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
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"Saved report: {output_path}")