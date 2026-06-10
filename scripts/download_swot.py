#!/usr/bin/env python3

#example command: python download_swot.py --start 2023-10-01 --end 2023-10-31
"""
download_swot.py

Downloads SWOT L3 LR SSH Expert data from AVISO using altimetry-downloader-aviso.

This script does NOT filter by Gulf Stream bounding box yet because the AVISO
downloader filters by product/date/cycle/pass, not bbox. Bbox filtering will
happen later in a separate script after the NetCDF files are downloaded.
"""

import argparse
import subprocess
from pathlib import Path


def run_command(command: list[str]) -> None:
    """Run a shell command and raise an error if it fails."""
    print("\nRunning command:")
    print(" ".join(command))
    print()

    result = subprocess.run(command, check=False)

    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download SWOT data from AVISO into a local output folder."
    )

    parser.add_argument(
        "--product",
        default="SWOT_L3_LR_SSH_Expert",
        help="AVISO product short name.",
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--output",
        default=str(Path.home() / "Documents" / "MOSAICS-2026" / "SWOT-Data"),
        help="Output directory for downloaded NetCDF files.",
    )

    parser.add_argument(
        "--cycle",
        default=None,
        help="Optional SWOT cycle number or range, e.g. 7 or 7,8.",
    )

    parser.add_argument(
        "--pass-num",
        default=None,
        help="Optional SWOT pass number or range, e.g. 123 or 12-14,21.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing downloaded files.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "micromamba",
        "run",
        "-n",
        "base",
        "altimetry-downloader-aviso",
        "get",
        args.product,
        "--output",
        str(output_dir),
        "--start",
        args.start,
        "--end",
        args.end,
    ]

    if args.cycle:
        command.extend(["--cycle", args.cycle])

    if args.pass_num:
        command.extend(["--pass", args.pass_num])

    if args.overwrite:
        command.append("--overwrite")

    run_command(command)

    print("\nDownload complete.")
    print(f"Files saved to: {output_dir}")


if __name__ == "__main__":
    main()