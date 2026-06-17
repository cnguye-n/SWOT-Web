"""Load one already-downloaded SWOT NetCDF file.
RETURNS SWOTPASSDATA which contains the native arrays and metadata
This module does not download data from Earthaccess or AVISO.

Its responsibility is:

    local NetCDF file
            ↓
    structured SwotPassData object
"""

from pathlib import Path

import numpy as np
import xarray as xr

from .data_models import SwotPassData


def wrap_longitudes(longitude: np.ndarray) -> np.ndarray:
    """Convert longitude values to the -180 to 180 convention.

    Some satellite products use 0 to 360 degrees.

    Example:
        279 degrees becomes -81 degrees.
    """

    return ((longitude + 180.0) % 360.0) - 180.0


def optional_array(
    dataset: xr.Dataset,
    variable_name: str,
) -> np.ndarray | None:
    """Read an optional NetCDF variable.

    Returns None when the variable is not present.
    """

    if variable_name not in dataset:
        return None

    return np.asarray(dataset[variable_name].values)


def load_swot_pass(
    source_path: Path,
    variable_name: str = "ssha_unfiltered",
) -> SwotPassData:
    """Open one SWOT file and load the arrays needed by the pipeline."""

    source_path = source_path.expanduser().resolve()

    if not source_path.exists():
        raise FileNotFoundError(
            f"SWOT NetCDF file not found: {source_path}"
        )

    print(f"Opening NetCDF: {source_path}")

    # The with block automatically closes the NetCDF after loading.
    with xr.open_dataset(
        source_path,
        mask_and_scale=True,
        decode_times=False,
    ) as dataset:

        required_variables = [
            "longitude",
            "latitude",
            variable_name,
        ]

        missing_variables = [
            name
            for name in required_variables
            if name not in dataset
        ]

        if missing_variables:
            raise KeyError(
                f"Missing required variables: {missing_variables}\n"
                f"Available variables: {list(dataset.variables)}"
            )

        longitude = wrap_longitudes(
            np.asarray(
                dataset["longitude"].values,
                dtype=np.float64,
            )
        )

        latitude = np.asarray(
            dataset["latitude"].values,
            dtype=np.float64,
        )

        values = np.asarray(
            dataset[variable_name].values,
            dtype=np.float64,
        )

        # These three arrays must describe the same native SWOT grid.
        if not (
            longitude.shape
            == latitude.shape
            == values.shape
        ):
            raise ValueError(
                "Longitude, latitude, and the selected variable "
                "must have the same shape.\n"
                f"Longitude: {longitude.shape}\n"
                f"Latitude:  {latitude.shape}\n"
                f"Values:    {values.shape}"
            )

        quality_flag = optional_array(
            dataset,
            "quality_flag",
        )

        if (
            quality_flag is not None
            and quality_flag.shape != values.shape
        ):
            raise ValueError(
                "quality_flag does not have the same shape "
                "as the SSHA array."
            )

        # Copy the global attributes before the dataset closes.
        attributes = dict(dataset.attrs)

        units = str(
            dataset[variable_name].attrs.get(
                "units",
                "",
            )
        )

        swot_pass = SwotPassData(
            source_path=source_path,
            variable_name=variable_name,
            units=units,
            longitude=longitude,
            latitude=latitude,
            values=values,
            quality_flag=quality_flag,
            cross_track_distance=optional_array(
                dataset,
                "cross_track_distance",
            ),
            i_num_line=optional_array(
                dataset,
                "i_num_line",
            ),
            i_num_pixel=optional_array(
                dataset,
                "i_num_pixel",
            ),
            attributes=attributes,
        )

    print("Loaded SWOT pass")
    print(f"  Variable: {swot_pass.variable_name}")
    print(f"  Units:    {swot_pass.units or 'not specified'}")
    print(f"  Shape:    {swot_pass.values.shape}")

    return swot_pass