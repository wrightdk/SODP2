"""
police_crime_stats.py — computes crime_count from the crime records
ingest/police_crime.py already fetched and filtered.

Trivial today (just a count), but it's still a derived number, and per
CLAUDE.md rule 1 those get computed in /pipeline/, not /ingest/ — keeping
even a one-line derivation here (rather than leaving it in ingest/) is
what makes the boundary a rule instead of a judgment call per source.

Usage:
    python pipeline/police_crime_stats.py --config config/salisbury.yml
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import latest_processed_path, merge_fields

import yaml


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    args = parser.parse_args()

    config = load_config(args.config)
    slug = config["locality"]["slug"]

    path = latest_processed_path(slug, "police_crime")
    crimes = json.loads(path.read_text(encoding="utf-8"))["crimes"]
    data = merge_fields(path, crime_count=len(crimes))
    print(f"crime_count = {data['crime_count']} for {slug} ({data['month']}) in {path}")


if __name__ == "__main__":
    main()
