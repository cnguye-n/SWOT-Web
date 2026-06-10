#!/usr/bin/env python3

import argparse
from pathlib import Path
import xarray as xr
#example command:micromamba run -n base python scripts/inspect_swot_netcdf.py ~/Documents/MOSAICS-2026/SWOT-Data/SWOT_L3_LR_SSH_Expert_013_147_20240401T194600_20240401T203727_v3.0.nc

def main():
    parser = argparse.ArgumentParser(description="Inspect a SWOT NetCDF file.")
    parser.add_argument("file", help="Path to SWOT NetCDF file.")
    args = parser.parse_args()

    nc_path = Path(args.file).expanduser().resolve()

    if not nc_path.exists():
        raise FileNotFoundError(f"File not found: {nc_path}")

    print(f"\nOpening: {nc_path}\n")

    ds = xr.open_dataset(nc_path)

    print("=== Dataset summary ===")
    print(ds)

    print("\n=== Coordinates ===")
    for name in ds.coords:
        print(name, ds.coords[name].shape, ds.coords[name].dtype)

    print("\n=== Data variables ===")
    for name in ds.data_vars:
        var = ds[name]
        print(name, var.shape, var.dtype)

    print("\n=== Global attributes ===")
    for key, value in ds.attrs.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()