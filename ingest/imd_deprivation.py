"""
imd_deprivation.py — joins the English Indices of Deprivation (IMD)
against a locality's `lsoa_codes`.

Unlike every other script in /ingest/, this one makes no network
request: the source file is a full England-wide release (~1,500 LSOAs
per rough decile band across ~35,000 LSOAs total), already downloaded
by hand into data/raw/imd_deprivation/ — see CLAUDE.md on why IMD is
joined here rather than resolved once at onboarding. This script only
parses and filters it.

English IMD only: this reads the "IMD25" sheet of the IoD2025 workbook
(LSOA code / rank / decile columns). A Welsh locality would need WIMD
instead — different file, different columns, not handled here.

The locality-level "average decile" is an unweighted mean of decile
across the locality's matched LSOAs, not a population-weighted score —
simpler than MHCLG's official area-summary methodology, and labelled as
such in the output so nobody mistakes it for an official summary figure.

Usage:
    python ingest/imd_deprivation.py --config config/salisbury.yml
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import yaml

SOURCE_URL = "https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025"
RAW_DIR = Path("data/raw/imd_deprivation")
SHEET_NAME = "IMD25"


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_raw_workbook() -> Path:
    candidates = sorted(RAW_DIR.glob("*.xlsx"))
    if not candidates:
        raise FileNotFoundError(
            f"No .xlsx found in {RAW_DIR} — download the IMD release workbook there first. See {SOURCE_URL}."
        )
    return candidates[0]


def release_label(workbook_path: Path) -> str:
    """e.g. 'File_1_IoD2025_...' -> 'IoD2025'; falls back to the filename stem."""
    match = re.search(r"IoD\d{4}", workbook_path.stem)
    return match.group(0) if match else workbook_path.stem


def load_lsoa_deciles(workbook_path: Path, lsoa_codes: set):
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]

    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    idx = {name: i for i, name in enumerate(header)}
    code_col = idx["LSOA code (2021)"]
    name_col = idx["LSOA name (2021)"]
    rank_col = idx["Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)"]
    decile_col = next(i for name, i in idx.items() if name.startswith("Index of Multiple Deprivation (IMD) Decile"))

    matched = []
    for row in rows:
        code = row[code_col]
        if code in lsoa_codes:
            matched.append(
                {
                    "lsoa_code": code,
                    "lsoa_name": row[name_col],
                    "imd_rank": row[rank_col],
                    "imd_decile": row[decile_col],
                }
            )
    return matched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("imd_deprivation", {})
    if not source_config.get("enabled"):
        print(f"imd_deprivation is disabled in {args.config} — nothing to do.")
        return

    geography_key = source_config.get("geography_key", "lsoa_codes")
    lsoa_codes = config["geography"].get(geography_key)
    if not lsoa_codes:
        raise ValueError(f"config.geography.{geography_key} is empty — nothing to join IMD against.")

    slug = config["locality"]["slug"]
    workbook_path = find_raw_workbook()
    release = release_label(workbook_path)

    matched = load_lsoa_deciles(workbook_path, set(lsoa_codes))
    if not matched:
        raise RuntimeError(f"None of config.geography.{geography_key} were found in {workbook_path} — check the file matches this release.")
    if len(matched) < len(lsoa_codes):
        missing = set(lsoa_codes) - {m["lsoa_code"] for m in matched}
        print(f"WARNING: {len(missing)} of {len(lsoa_codes)} lsoa_codes not found in {workbook_path}: {sorted(missing)}")

    average_decile = round(sum(m["imd_decile"] for m in matched) / len(matched))
    fetched_at = datetime.fromtimestamp(workbook_path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    processed_dir = Path("data/processed") / slug / "imd_deprivation"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / f"{release}.json"
    processed_path.write_text(
        json.dumps(
            {
                "source_url": SOURCE_URL,
                "fetched_at": fetched_at,
                "locality": slug,
                "release": release,
                "filter": {"method": geography_key, "lsoa_code_count": len(lsoa_codes)},
                "average_decile": average_decile,
                "average_decile_method": "unweighted mean of IMD decile across matched LSOAs",
                "lsoa_count_matched": len(matched),
                "lsoas": sorted(matched, key=lambda m: m["lsoa_code"]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote IMD decile {average_decile} ({len(matched)} LSOAs) for {slug} ({release}) to {processed_path}")


if __name__ == "__main__":
    main()
