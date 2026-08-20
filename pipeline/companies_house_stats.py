"""
companies_house_stats.py — computes company_count and active_count from
the company list ingest/companies_house.py already fetched and filtered.

Usage:
    python pipeline/companies_house_stats.py --config config/salisbury.yml
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

    path = latest_processed_path(slug, "companies_house")
    companies = json.loads(path.read_text(encoding="utf-8"))["companies"]
    active_count = sum(1 for c in companies if c["company_status"] == "active")
    data = merge_fields(path, company_count=len(companies), active_count=active_count)
    print(f"company_count = {data['company_count']}, active_count = {data['active_count']} for {slug} ({data['month']}) in {path}")


if __name__ == "__main__":
    main()
