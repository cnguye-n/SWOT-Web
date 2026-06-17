"""Reusable tools for processing SWOT NetCDF files.

The package separates the major processing responsibilities:

- dataset.py: read a local NetCDF file
- quality.py: decide which measurements are valid
- raster.py: resample the SWOT swath and write a COG
- nadir.py: create the separate nadir GeoJSON
- diagnostics.py: create preview images and reports
- data_models.py: shared structured data containers
"""