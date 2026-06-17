"""Shared data classes for the SWOT preprocessing pipeline.

These classes are data containers used to pass organized information
between modules.
"""
from __future__ import annotations #tells python to delay evaluating type hints until they are needed

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


#geographic bounding box:
#west longitude, south latitude, east longitude, north latitude.
BoundingBox = tuple[float, float, float, float]


@dataclass
class SwotPassData:
    """Native arrays and metadata loaded from one SWOT NetCDF file"""

    #Original NetCDF file
    source_path: Path

    #Name of the plotted variable, ex. ssha_unfiltered
    variable_name: str

    #Units stored in the NetCDF variable metadata
    units: str

    #Native two-dimensional SWOT arrays
    longitude: np.ndarray
    latitude: np.ndarray
    values: np.ndarray

    #variables used for quality control and nadir mapping
    quality_flag: np.ndarray | None
    cross_track_distance: np.ndarray | None
    i_num_line: np.ndarray | None
    i_num_pixel: np.ndarray | None

    #Global NetCDF attributes, ex. time coverage
    attributes: dict[str, Any]


@dataclass(frozen=True)
class RasterConfig:
    """Settings used to create regular output raster"""
    bbox: BoundingBox

    #Geographic output-grid spacing
    #0.0025 degrees is only the output display grid. It does not turn
    #a 2-km source product into scientifically independent 250-m data.
    resolution_deg: float = 0.0025

    #Pyresample search radius in meters
    #None means raster.py will estimate a suitable radius from the
    #native source spacing.
    radius_m: float | None = None

    #Value written wherever no valid source measurement is available
    nodata: float = -9999.0

    #Safety limit to prevent accidentally constructing an enormous
    #global raster at a very small geographic resolution.
    max_cells: int = 50_000_000


@dataclass
class RasterResult:
    """Resampled raster and its spatial information"""

    data: np.ndarray
    bbox: BoundingBox
    width: int
    height: int

    #Requested output-grid spacing
    resolution_deg: float

    #Estimated posting distance of the original SWOT data
    source_spacing_m: float

    #Actual Pyresample search radius used
    radius_m: float

    #Nodata value used when writing the file
    nodata: float


@dataclass
class NadirTrack:
    """Mapped SWOT nadir observations.

    Invalid positions stay as NaN so that the gaps in the original data
    become breaks in the GeoJSON line and it is not smoothed over in the visualization
    """

    longitude: np.ndarray
    latitude: np.ndarray
    values: np.ndarray