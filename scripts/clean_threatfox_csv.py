#!/usr/bin/env python3
"""
Utility script to clean and normalize ThreatFox CSV dumps.

Removes metadata headers/footers and standardizes quoting so that
tools like DuckDB, VS Code CSV viewer, Pandas, and Polars can read
it without parsing errors.
"""
import csv
import sys
from pathlib import Path


def clean_threatfox_csv(input_path: str, output_path: str = None) -> None:
    in_file = Path(input_path)
    if not in_file.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    out_file = Path(output_path) if output_path else in_file

    print(f"Reading {in_file}...")
    with open(in_file, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    header_idx = None
    for i, line in enumerate(lines):
        if "first_seen_utc" in line and "ioc_value" in line:
            header_idx = i
            break

    if header_idx is None:
        print("Error: Could not locate header row in file.")
        sys.exit(1)

    header_line = lines[header_idx].lstrip("# ").strip()
    # Filter out any trailing comments or non-data lines
    raw_data_lines = [
        line for line in lines[header_idx + 1 :]
        if not line.strip().startswith("#") and line.strip()
    ]

    print(f"Found {len(raw_data_lines)} data rows. Normalizing columns...")
    reader = csv.reader([header_line] + raw_data_lines, skipinitialspace=True)

    with open(out_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        for row in reader:
            writer.writerow(row)

    print(f"Successfully cleaned and wrote standard CSV to: {out_file}")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/full.csv"
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    clean_threatfox_csv(src, dst)
