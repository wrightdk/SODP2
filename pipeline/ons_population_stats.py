"""
ons_population_stats.py — sums the per-LSOA population estimates
ingest/ons_population.py already fetched into a locality total.

This is the number the homepage card and the site's summary copy read —
CLAUDE.md rule 1 puts it here, not in ingest/, so there's one place that
does this addition rather than every consumer summing by_lsoa itself.

Usage:
    python pipeline/ons_population_stats.py --config config/salisbury.yml
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

    path = latest_processed_path(slug, "ons_population")
    by_lsoa = json.loads(path.read_text(encoding="utf-8"))["by_lsoa"]
    total = sum(l["population"] for l in by_lsoa)
    data = merge_fields(path, population=total)
    print(f"population = {data['population']:,} for {slug} ({data['year']}) in {path}")


if __name__ == "__main__":
    main()
