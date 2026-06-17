#!/usr/bin/env python3
"""Diagnosable SWOT L3 swath -> GeoTIFF/COG conversion.

This script follows the same staged logic as SWOTPass_FigureGenerator.ipynb:

    1. open and inspect the NetCDF
    2. load native 2-D longitude/latitude/SSHA arrays
    3. normalize longitude and units
    4. apply explicit quality control
    5. clip by masking, without reshaping the native swath
    6. diagnose native spacing and mapped nadir positions
    7. preview the native swath
    8. resample with pyresample nearest-neighbour
    9. preview and validate the output raster
    10. write GeoTIFF or COG plus a JSON diagnostic report

Nearest-neighbour resampling copies existing source values. It does not blend,
smooth, or linearly interpolate SSHA values.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import xarray as xr
from pyresample import geometry, kd_tree
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

NODATA = -9999.0
EARTH_RADIUS_M = 6_371_008.8


@dataclass
class SwotArrays:
    """Native SWOT arrays and optional mapped-nadir information."""

    longitude: np.ndarray
    latitude: np.ndarray
    values: np.ndarray
    quality_flag: np.ndarray | None
    cross_track_distance: np.ndarray | None
    i_num_line: np.ndarray | None
    i_num_pixel: np.ndarray | None
    nadir_lon: np.ndarray | None
    nadir_lat: np.ndarray | None
    nadir_values: np.ndarray | None
    units: str


@dataclass
class RasterResult:
    """Resampled raster and the grid information used to create it."""

    data: np.ndarray
    bbox: tuple[float, float, float, float]
    width: int
    height: int
    spacing_m: float
    radius_m: float


def parse_quality_values(text: str) -> tuple[int, ...]:
    """Parse a comma-separated quality list such as '0,3'."""
    try:
        values = tuple(sorted({int(part.strip()) for part in text.split(",") if part.strip()}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Quality values must be comma-separated integers.") from exc
    if not values:
        raise argparse.ArgumentTypeError("At least one quality value is required.")
    return values


def wrap_longitudes(longitude: np.ndarray) -> np.ndarray:
    """Convert longitude to [-180, 180)."""
    return ((longitude + 180.0) % 360.0) - 180.0


def open_swot_dataset(path: Path) -> xr.Dataset:
    """Open a SWOT NetCDF with scale factors and fill values decoded."""
    return xr.open_dataset(path, mask_and_scale=True, decode_times=False)


def inspect_dataset(ds: xr.Dataset, variable: str) -> dict[str, Any]:
    """Return and print a compact dataset inventory before processing."""
    required = ["longitude", "latitude", variable]
    missing = [name for name in required if name not in ds]
    if missing:
        raise KeyError(f"Missing required variables: {missing}. Available: {list(ds.variables)}")

    important = [
        "longitude", "latitude", variable, "quality_flag",
        "cross_track_distance", "i_num_line", "i_num_pixel", "time",
    ]
    inventory: dict[str, Any] = {
        "dimensions": {name: int(size) for name, size in ds.sizes.items()},
        "variables": {},
    }

    print("\n[1/10] Dataset inspection")
    print("Dimensions:", inventory["dimensions"])
    for name in important:
        if name not in ds:
            continue
        da = ds[name]
        item = {
            "shape": list(da.shape),
            "dtype": str(da.dtype),
            "units": str(da.attrs.get("units", "")),
        }
        inventory["variables"][name] = item
        print(f"  {name:22s} shape={str(da.shape):16s} dtype={str(da.dtype):10s} units={item['units']}")
    return inventory


def extract_mapped_nadir(
    longitude: np.ndarray,
    latitude: np.ndarray,
    values: np.ndarray,
    i_num_line: np.ndarray | None,
    i_num_pixel: np.ndarray | None,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    """Map L3 nadir indices back to their corresponding 2-D KaRIn cells."""
    if i_num_line is None or i_num_pixel is None:
        return None, None, None

    lines = np.asarray(i_num_line).astype(np.int64, copy=False)
    pixels = np.asarray(i_num_pixel).astype(np.int64, copy=False)
    ok = (
        (lines >= 0) & (lines < longitude.shape[0])
        & (pixels >= 0) & (pixels < longitude.shape[1])
    )
    lines = lines[ok]
    pixels = pixels[ok]
    return longitude[lines, pixels], latitude[lines, pixels], values[lines, pixels]


def load_native_arrays(ds: xr.Dataset, variable: str) -> SwotArrays:
    """Load native arrays, normalize longitudes, and reconstruct mapped nadir."""
    print("\n[2/10] Loading native SWOT arrays")
    longitude = wrap_longitudes(np.asarray(ds["longitude"].values, dtype=np.float64))
    latitude = np.asarray(ds["latitude"].values, dtype=np.float64)
    values = np.asarray(ds[variable].values, dtype=np.float64)

    if longitude.shape != latitude.shape or longitude.shape != values.shape:
        raise ValueError(
            f"longitude, latitude, and {variable} must share one 2-D shape; "
            f"got {longitude.shape}, {latitude.shape}, {values.shape}."
        )

    quality = np.asarray(ds["quality_flag"].values) if "quality_flag" in ds else None
    cross_track = np.asarray(ds["cross_track_distance"].values) if "cross_track_distance" in ds else None
    i_line = np.asarray(ds["i_num_line"].values) if "i_num_line" in ds else None
    i_pixel = np.asarray(ds["i_num_pixel"].values) if "i_num_pixel" in ds else None
    nadir_lon, nadir_lat, nadir_values = extract_mapped_nadir(
        longitude, latitude, values, i_line, i_pixel
    )

    print("Native grid shape:", values.shape)
    if cross_track is not None and cross_track.ndim == 1:
        center_column = int(np.nanargmin(np.abs(cross_track)))
        print("Cross-track center column:", center_column)
        print("Center distance:", float(cross_track[center_column]), ds["cross_track_distance"].attrs.get("units", ""))
    if nadir_lon is not None:
        print("Mapped nadir observations:", int(np.count_nonzero(np.isfinite(nadir_lon) & np.isfinite(nadir_lat))))

    return SwotArrays(
        longitude=longitude,
        latitude=latitude,
        values=values,
        quality_flag=quality,
        cross_track_distance=cross_track,
        i_num_line=i_line,
        i_num_pixel=i_pixel,
        nadir_lon=nadir_lon,
        nadir_lat=nadir_lat,
        nadir_values=nadir_values,
        units=str(ds[variable].attrs.get("units", "")),
    )


def build_valid_mask(
    arrays: SwotArrays,
    quality_values: tuple[int, ...],
    use_quality_mask: bool,
    value_min: float | None,
    value_max: float | None,
) -> np.ndarray:
    """Build one explicit source-validity mask for all later stages."""
    print("\n[3/10] Applying source quality control")
    valid = (
        np.isfinite(arrays.longitude)
        & np.isfinite(arrays.latitude)
        & np.isfinite(arrays.values)
        & (arrays.latitude >= -90.0)
        & (arrays.latitude <= 90.0)
    )

    if use_quality_mask:
        if arrays.quality_flag is None:
            print("Warning: quality mask requested, but quality_flag is unavailable.")
        else:
            valid &= np.isin(arrays.quality_flag, quality_values)
            print("Accepted quality flags:", quality_values)

    if value_min is not None:
        valid &= arrays.values >= value_min
    if value_max is not None:
        valid &= arrays.values <= value_max

    print(f"Valid native cells: {int(valid.sum()):,} / {valid.size:,}")
    return valid


def normalize_bbox(bbox: Iterable[float]) -> tuple[float, float, float, float]:
    west, south, east, north = map(float, bbox)
    if not (-180 <= west < east <= 180):
        raise ValueError("BBox must satisfy -180 <= west < east <= 180.")
    if not (-90 <= south < north <= 90):
        raise ValueError("BBox must satisfy -90 <= south < north <= 90.")
    return west, south, east, north


def derive_bbox(longitude: np.ndarray, latitude: np.ndarray, valid: np.ndarray, pad_deg: float = 0.05) -> tuple[float, float, float, float]:
    """Derive output bounds from valid native cells."""
    lon = longitude[valid]
    lat = latitude[valid]
    if lon.size == 0:
        raise ValueError("No valid source coordinates remain.")
    if np.nanmax(lon) - np.nanmin(lon) > 180:
        raise ValueError("Pass crosses the antimeridian; provide a regional --bbox.")
    return (
        max(-180.0, float(np.nanmin(lon)) - pad_deg),
        max(-90.0, float(np.nanmin(lat)) - pad_deg),
        min(180.0, float(np.nanmax(lon)) + pad_deg),
        min(90.0, float(np.nanmax(lat)) + pad_deg),
    )


def apply_bbox_mask(
    longitude: np.ndarray,
    latitude: np.ndarray,
    valid: np.ndarray,
    bbox: tuple[float, float, float, float],
) -> np.ndarray:
    """Clip by masking native cells; do not reshape the swath."""
    print("\n[4/10] Applying geographic mask")
    west, south, east, north = bbox
    inside = (
        (longitude >= west) & (longitude <= east)
        & (latitude >= south) & (latitude <= north)
    )
    clipped = valid & inside
    rows = np.where(np.any(clipped, axis=1))[0]
    print("Output bbox:", bbox)
    print("Native rows intersecting bbox:", int(rows.size))
    print("Valid cells inside bbox:", int(clipped.sum()))
    if not np.any(clipped):
        raise ValueError("No valid source cells intersect the output bbox.")
    return clipped


def haversine_m(lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Great-circle distance in meters."""
    lon1r, lat1r, lon2r, lat2r = map(np.deg2rad, (lon1, lat1, lon2, lat2))
    dlon = lon2r - lon1r
    dlat = lat2r - lat1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def estimate_source_spacing_m(longitude: np.ndarray, latitude: np.ndarray, valid: np.ndarray) -> float:
    """Estimate native posting from valid along- and across-track neighbors."""
    print("\n[5/10] Diagnosing native spacing")
    samples: list[np.ndarray] = []

    pairs = [
        ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
        ((slice(None), slice(None, -1)), (slice(None), slice(1, None))),
    ]
    for first, second in pairs:
        pair_valid = valid[first] & valid[second]
        if np.any(pair_valid):
            distances = haversine_m(
                longitude[first][pair_valid], latitude[first][pair_valid],
                longitude[second][pair_valid], latitude[second][pair_valid],
            )
            samples.append(distances)

    if not samples:
        raise ValueError("Could not estimate source spacing.")
    distances = np.concatenate(samples)
    distances = distances[np.isfinite(distances) & (distances > 0)]
    cutoff = np.nanpercentile(distances, 75)
    typical = distances[distances <= cutoff]
    spacing = float(np.nanmedian(typical))
    print(f"Estimated typical native spacing: {spacing:,.1f} m")
    return spacing


def build_target_area(
    bbox: tuple[float, float, float, float],
    resolution_deg: float,
) -> tuple[geometry.AreaDefinition, int, int]:
    """Build a regular EPSG:4326 target area."""
    west, south, east, north = bbox
    width = max(1, math.ceil((east - west) / resolution_deg))
    height = max(1, math.ceil((north - south) / resolution_deg))
    area = geometry.AreaDefinition(
        "swot_target", "SWOT swath output", "epsg4326", "EPSG:4326",
        width, height, (west, south, east, north),
    )
    return area, width, height


def resample_swath_nearest(
    arrays: SwotArrays,
    valid: np.ndarray,
    bbox: tuple[float, float, float, float],
    resolution_deg: float,
    radius_m: float | None,
    epsilon: float,
) -> RasterResult:
    """Nearest-neighbour swath resampling with an explicit physical radius."""
    print("\n[6/10] Resampling native swath")
    spacing = estimate_source_spacing_m(arrays.longitude, arrays.latitude, valid)
    radius = float(radius_m) if radius_m is not None else 1.5 * spacing
    if radius <= 0:
        raise ValueError("radius_m must be positive.")

    area, width, height = build_target_area(bbox, resolution_deg)
    source = geometry.SwathDefinition(lons=arrays.longitude, lats=arrays.latitude)
    masked_values = np.ma.array(arrays.values, mask=~valid)

    print(f"Search radius: {radius:,.1f} m")
    print(f"Output grid: {width:,} x {height:,} at {resolution_deg} degrees")
    result = kd_tree.resample_nearest(
        source_geo_def=source,
        data=masked_values,
        target_geo_def=area,
        radius_of_influence=radius,
        epsilon=epsilon,
        fill_value=None,
        reduce_data=True,
    )
    data = np.asarray(np.ma.filled(result, np.nan), dtype=np.float32)
    print(f"Finite output pixels: {int(np.count_nonzero(np.isfinite(data))):,}")
    return RasterResult(data, bbox, width, height, spacing, radius)


def subset_nadir_for_bbox(arrays: SwotArrays, bbox: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Return valid mapped-nadir positions within the selected bbox."""
    if arrays.nadir_lon is None or arrays.nadir_lat is None:
        return np.array([]), np.array([])
    west, south, east, north = bbox
    ok = (
        np.isfinite(arrays.nadir_lon) & np.isfinite(arrays.nadir_lat)
        & (arrays.nadir_lon >= west) & (arrays.nadir_lon <= east)
        & (arrays.nadir_lat >= south) & (arrays.nadir_lat <= north)
    )
    return arrays.nadir_lon[ok], arrays.nadir_lat[ok]


def save_native_preview(
    path: Path,
    arrays: SwotArrays,
    valid: np.ndarray,
    bbox: tuple[float, float, float, float],
    variable: str,
    display_min: float,
    display_max: float,
) -> None:
    """Plot native pcolormesh exactly before regular-grid resampling."""
    print("\n[7/10] Saving native-swath diagnostic preview")
    native = np.where(valid, arrays.values, np.nan)
    nadir_lon, nadir_lat = subset_nadir_for_bbox(arrays, bbox)

    fig, ax = plt.subplots(figsize=(7.2, 10.0), dpi=160)
    mesh = ax.pcolormesh(
        arrays.longitude, arrays.latitude, native,
        cmap="RdBu_r", vmin=display_min, vmax=display_max,
        shading="auto", rasterized=True,
    )
    if nadir_lon.size:
        ax.plot(nadir_lon, nadir_lat, color="white", linewidth=3.0, alpha=0.9)
        ax.plot(nadir_lon, nadir_lat, color="#ef8f73", linewidth=1.2, linestyle=(0, (1.2, 2.0)))
    west, south, east, north = bbox
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Native SWOT swath before resampling\n{variable}")
    cbar = fig.colorbar(mesh, ax=ax, orientation="horizontal", pad=0.07)
    cbar.set_label(f"{variable} ({arrays.units or 'source units'})")
    fig.savefig(path, dpi=250, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("Saved:", path)


def save_resampled_preview(
    path: Path,
    result: RasterResult,
    variable: str,
    units: str,
    display_min: float,
    display_max: float,
) -> None:
    """Plot the regular raster after resampling for direct comparison."""
    print("\n[8/10] Saving resampled-raster diagnostic preview")
    west, south, east, north = result.bbox
    fig, ax = plt.subplots(figsize=(7.2, 10.0), dpi=160)
    image = ax.imshow(
        result.data,
        extent=(west, east, south, north),
        origin="upper",
        cmap="RdBu_r",
        vmin=display_min,
        vmax=display_max,
        interpolation="nearest",
        aspect="auto",
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Pyresample nearest-neighbour raster\n{variable}")
    cbar = fig.colorbar(image, ax=ax, orientation="horizontal", pad=0.07)
    cbar.set_label(f"{variable} ({units or 'source units'})")
    fig.savefig(path, dpi=250, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("Saved:", path)


def write_geotiff(
    path: Path,
    result: RasterResult,
    variable: str,
    units: str,
    source_file: Path,
    quality_values: tuple[int, ...],
) -> None:
    """Write the resampled raster as a tiled compressed GeoTIFF."""
    print("\n[9/10] Writing GeoTIFF")
    west, south, east, north = result.bbox
    transform = from_bounds(west, south, east, north, result.width, result.height)
    encoded = np.where(np.isfinite(result.data), result.data, NODATA).astype(np.float32)

    profile = {
        "driver": "GTiff", "height": result.height, "width": result.width,
        "count": 1, "dtype": "float32", "crs": "EPSG:4326",
        "transform": transform, "nodata": NODATA,
        "compress": "DEFLATE", "predictor": 3, "tiled": True,
        "blockxsize": 512, "blockysize": 512, "BIGTIFF": "IF_SAFER",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(encoded, 1)
        dst.set_band_description(1, variable)
        dst.update_tags(
            source_file=source_file.name,
            source_variable=variable,
            source_units=units,
            processing="pyresample_nearest_neighbour",
            estimated_source_spacing_m=f"{result.spacing_m:.3f}",
            radius_of_influence_m=f"{result.radius_m:.3f}",
            accepted_quality_flags=",".join(map(str, quality_values)),
        )


def convert_to_cog(source_tif: Path, output_cog: Path) -> None:
    """Convert a GeoTIFF to a Cloud Optimized GeoTIFF without changing values."""
    with rasterio.open(source_tif) as src:
        profile = src.profile.copy()
        profile.update(
            driver="COG", compress="DEFLATE", predictor=3,
            blocksize=512, overview_resampling=Resampling.nearest,
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(output_cog, "w", **profile) as dst:
            dst.write(src.read())
            dst.update_tags(**src.tags())
            dst.set_band_description(1, src.descriptions[0])


def validate_raster(path: Path) -> dict[str, Any]:
    """Reopen the written file and report geospatial and value diagnostics."""
    print("\n[10/10] Validating written raster")
    with rasterio.open(path) as src:
        band = src.read(1, masked=True)
        finite = band.compressed()
        report = {
            "driver": src.driver,
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
            "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
            "transform": list(src.transform)[:6],
            "nodata": src.nodata,
            "valid_output_pixels": int(finite.size),
            "output_min": float(np.nanmin(finite)) if finite.size else None,
            "output_max": float(np.nanmax(finite)) if finite.size else None,
        }
    for key, value in report.items():
        print(f"  {key}: {value}")
    return report


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Diagnostic report:", path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input SWOT L3 NetCDF")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Optional output .tif path. Default: save beside this script.")
    parser.add_argument("--variable", default="ssha_unfiltered")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--resolution-deg", type=float, default=0.01)
    parser.add_argument("--radius-m", type=float, default=None)
    parser.add_argument("--epsilon", type=float, default=0.0)
    parser.add_argument("--quality-values", type=parse_quality_values, default=(0, 3), help="Accepted flags, default: 0,3")
    parser.add_argument("--no-quality-mask", action="store_true")
    parser.add_argument("--value-min", type=float, default=-2.0)
    parser.add_argument("--value-max", type=float, default=2.0)
    parser.add_argument("--display-min", type=float, default=-0.2)
    parser.add_argument("--display-max", type=float, default=0.2)
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional folder for every generated file. Default: the folder containing this script.")
    parser.add_argument("--cog", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(args.input)
    if args.resolution_deg <= 0:
        raise ValueError("--resolution-deg must be positive.")
    if args.display_min >= args.display_max:
        raise ValueError("--display-min must be less than --display-max.")

    # Keep every generated file together. By default, that is the same
    # scripts folder that contains this Python file.
    script_dir = Path(__file__).resolve().parent
    output_dir = (args.output_dir or script_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    input_stem = args.input.stem
    default_suffix = "_pyresample_cog.tif" if args.cog else "_pyresample.tif"
    output_path = (
        args.output.expanduser().resolve()
        if args.output is not None
        else output_dir / f"{input_stem}_{args.variable}{default_suffix}"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    native_preview = output_dir / f"{input_stem}_{args.variable}_01_native_swath.png"
    resampled_preview = output_dir / f"{input_stem}_{args.variable}_02_resampled_raster.png"
    report_path = output_dir / f"{input_stem}_{args.variable}_diagnostics.json"

    ds = open_swot_dataset(args.input)
    try:
        inventory = inspect_dataset(ds, args.variable)
        arrays = load_native_arrays(ds, args.variable)
        source_valid = build_valid_mask(
            arrays, args.quality_values, not args.no_quality_mask,
            args.value_min, args.value_max,
        )
        bbox = normalize_bbox(args.bbox) if args.bbox else derive_bbox(
            arrays.longitude, arrays.latitude, source_valid
        )
        clipped_valid = apply_bbox_mask(arrays.longitude, arrays.latitude, source_valid, bbox)

        save_native_preview(
            native_preview, arrays, clipped_valid, bbox, args.variable,
            args.display_min, args.display_max,
        )

        result = resample_swath_nearest(
            arrays, clipped_valid, bbox, args.resolution_deg,
            args.radius_m, args.epsilon,
        )

        save_resampled_preview(
            resampled_preview, result, args.variable, arrays.units,
            args.display_min, args.display_max,
        )

        if args.cog:
            with tempfile.TemporaryDirectory(prefix="swot_cog_") as temp_dir:
                intermediate = Path(temp_dir) / "intermediate.tif"
                write_geotiff(
                    intermediate, result, args.variable, arrays.units,
                    args.input, args.quality_values,
                )
                convert_to_cog(intermediate, output_path)
        else:
            write_geotiff(
                output_path, result, args.variable, arrays.units,
                args.input, args.quality_values,
            )

        raster_report = validate_raster(output_path)
        report = {
            "input": str(args.input.resolve()),
            "output": str(output_path.resolve()),
            "variable": args.variable,
            "source_units": arrays.units,
            "dataset_inventory": inventory,
            "accepted_quality_flags": list(args.quality_values),
            "quality_mask_enabled": not args.no_quality_mask,
            "source_valid_pixels_before_bbox": int(source_valid.sum()),
            "source_valid_pixels_inside_bbox": int(clipped_valid.sum()),
            "bbox": list(bbox),
            "requested_resolution_deg": args.resolution_deg,
            "estimated_source_spacing_m": result.spacing_m,
            "radius_of_influence_m": result.radius_m,
            "native_preview": str(native_preview.resolve()),
            "resampled_preview": str(resampled_preview.resolve()),
            "raster_validation": raster_report,
        }
        write_report(report_path, report)
    finally:
        ds.close()


if __name__ == "__main__":
    main()
