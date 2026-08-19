"""
fetch_lsoa_boundaries.py — one-off cache of LSOA boundary geometry for a
locality's `lsoa_codes`, for the choropleth charts in /pipeline/.

Like generate_locality_geography.py, this is run by hand when onboarding
a locality (or when its lsoa_codes change) — not part of the scheduled
ingestion workflow. Unlike that script, this doesn't resolve which LSOAs
belong to a locality; it takes an already-resolved `lsoa_codes` list from
config and fetches just their boundary shapes.

Source: ONS Open Geography Portal, "Lower layer Super Output Areas
(December 2021) Boundaries EW BSC (V4)" — the super-generalised (200m),
coastline-clipped resolution. Deliberately not the full-resolution BFC/BFE
versions: this is a small schematic map of ~28 LSOAs, not a precise GIS
product, and BSC is a small, fast, appropriately-detailed fetch — same
"query/filter, don't bulk-download" principle as the rest of this
project's geography handling (CLAUDE.md rule 3). Queried via the
FeatureServer's `where=<field> IN (...)` filter, same pattern as the
NSPL query described in CLAUDE.md's geography join plan step 6.

Usage:
    python fetch_lsoa_boundaries.py --config config/salisbury.yml
"""

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

FEATURE_SERVER = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BSC_V4/FeatureServer/0/query"
)


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_boundaries(lsoa_codes):
    codes_clause = ",".join(f"'{code}'" for code in lsoa_codes)
    params = {
        "where": f"LSOA21CD IN ({codes_clause})",
        "outFields": "LSOA21CD,LSOA21NM",
        "outSR": "4326",
        "f": "geojson",
    }
    url = f"{FEATURE_SERVER}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ONS Open Geography Portal returned {e.code} for {url}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach ONS Open Geography Portal at {url}: {e.reason}") from e

    features = data.get("features", [])
    if not features:
        raise RuntimeError(f"No boundaries returned for {url} — check the LSOA codes are 2021-vintage.")
    return data, url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    args = parser.parse_args()

    config = load_config(args.config)
    lsoa_codes = config["geography"].get("lsoa_codes")
    if not lsoa_codes:
        raise ValueError("config.geography.lsoa_codes is empty — nothing to fetch boundaries for.")

    slug = config["locality"]["slug"]
    geojson, source_url = fetch_boundaries(lsoa_codes)

    if len(geojson["features"]) < len(lsoa_codes):
        found = {f["properties"]["LSOA21CD"] for f in geojson["features"]}
        missing = set(lsoa_codes) - found
        print(f"WARNING: {len(missing)} of {len(lsoa_codes)} lsoa_codes had no boundary returned: {sorted(missing)}")

    geojson["_source_url"] = source_url

    out_path = Path("data/reference") / f"lsoa_boundaries_{slug}.geojson"
    out_path.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    print(f"Wrote {len(geojson['features'])} LSOA boundaries for {slug} to {out_path}")


if __name__ == "__main__":
    main()
