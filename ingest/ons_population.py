"""
ons_population.py — ingests mid-year population estimates for a locality,
summed across its `lsoa_codes`.

Why LSOA-level, not local-authority-level: a locality's `local_authority_codes`
cover the whole council area (e.g. all of Wiltshire, ~500,000 people) — the
same "Wiltshire vs Salisbury" problem the README calls this project's central
design decision, just previously unsolved for this one source. `lsoa_codes`
is the BUA's actual LSOA membership, so summing population across it gives a
town-scale figure instead. Same geography_key pattern as imd_deprivation.

Why Nomis, not api.beta.ons.gov.uk or a bulk download: ONS publishes small-
area population estimates as a single England+Wales workbook (~80MB) — the
kind of bulk download this project deliberately avoids (see CLAUDE.md rule
3, same principle as not downloading the full NSPL/ONSPD). Nomis serves the
identical data queryable by geography code, so a locality's ~28 LSOAs cost
one small request instead of an 80MB file.

Dataset: NM_2014_1 ("Population estimates - small area (2021 based) by
single year of age"), the current Census-2021-boundary small-area dataset —
NOT NM_2010_1, which is the older 2011-boundary version, or NM_31_1, the
local-authority-level dataset this replaced. Its dimension names also
differ from NM_31_1: `gender` (not `sex`) and `c_age` (not `age`) —
confirmed by trial against the live API, same as the sex/gender quirk
found on NM_31_1. `gender=0` is "Total", `c_age=0` is "All Ages",
`measures=20100` is "value" (not percent).

Small-area estimates lag district-level ones by about a year: confirmed
live, NM_31_1's "latest" was already mid-2025 while NM_2014_1's "latest"
was still mid-2024 — small-area figures are apportioned down from the
district totals after those are finalised, hence the extra lag. This is
annual data, not quarterly.

Caching: same approach as before — no separate cheap "what's latest"
endpoint, so the (still small, ~28-row) data query doubles as the check.
The result's resolved year is the cache key.

Usage:
    python ingest/ons_population.py --config config/salisbury.yml
"""

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

API_BASE = "https://www.nomisweb.co.uk/api/v01/dataset/NM_2014_1.data.json"
API_DOCS_URL = "https://www.nomisweb.co.uk/api/v01/about"


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_population(lsoa_codes, year: str | None):
    params = {
        "geography": ",".join(lsoa_codes),
        "date": year or "latest",
        "gender": "0",
        "c_age": "0",
        "measures": "20100",
    }
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Nomis API returned {e.code} for {url}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach Nomis API at {url}: {e.reason}") from e

    if "error" in data:
        raise RuntimeError(f"Nomis API error for {url}: {data['error']}")

    obs = data.get("obs", [])
    if not obs:
        raise RuntimeError(f"No population observations returned for {url}")
    return obs, url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    parser.add_argument("--year", default=None, help="Mid-year estimate year, e.g. 2024; defaults to Nomis's latest")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached raw pull exists for the year")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("ons_population", {})
    if not source_config.get("enabled"):
        print(f"ons_population is disabled in {args.config} — nothing to do.")
        return

    geography_key = source_config.get("geography_key", "lsoa_codes")
    lsoa_codes = config["geography"].get(geography_key)
    if not lsoa_codes:
        raise ValueError(f"config.geography.{geography_key} is empty — nothing to query Nomis with.")

    slug = config["locality"]["slug"]
    raw_dir = Path("data/raw/ons_population") / slug

    # If --year is given explicitly and already cached, skip the network
    # entirely. Otherwise we don't know the resolved year in advance, so
    # the (still small) data query doubles as the "what's latest" check —
    # see module docstring.
    cached_path = raw_dir / f"{args.year}.json" if args.year else None
    if cached_path and cached_path.exists() and not args.force:
        print(f"Using cached raw pull: {cached_path}")
        cached = json.loads(cached_path.read_text(encoding="utf-8"))
        write_processed(slug, args.year, cached["obs"], cached["source_url"], cached["fetched_at"], lsoa_codes, geography_key)
        return

    obs, source_url = fetch_population(lsoa_codes, args.year)
    year = str(obs[0]["time"]["value"])
    raw_path = raw_dir / f"{year}.json"

    if raw_path.exists() and not args.force:
        print(f"Already cached for {year}: {raw_path}")
        cached = json.loads(raw_path.read_text(encoding="utf-8"))
        obs, source_url, fetched_at = cached["obs"], cached["source_url"], cached["fetched_at"]
    else:
        raw_dir.mkdir(parents=True, exist_ok=True)
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_path.write_text(
            json.dumps({"source_url": source_url, "fetched_at": fetched_at, "obs": obs}, indent=2),
            encoding="utf-8",
        )
        print(f"Fetched population estimates for {year}, cached to {raw_path}")

    write_processed(slug, year, obs, source_url, fetched_at, lsoa_codes, geography_key)


def write_processed(slug, year, obs, source_url, fetched_at, lsoa_codes, geography_key):
    by_lsoa = [
        {
            "code": o["geography"]["value"],
            "name": o["geography"]["description"],
            "population": o["obs_value"]["value"],
        }
        for o in obs
    ]
    total = sum(l["population"] for l in by_lsoa)

    if len(by_lsoa) < len(lsoa_codes):
        missing = set(lsoa_codes) - {l["code"] for l in by_lsoa}
        print(f"WARNING: {len(missing)} of {len(lsoa_codes)} lsoa_codes had no observation returned: {sorted(missing)}")

    processed_dir = Path("data/processed") / slug / "ons_population"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / f"{year}.json"
    processed_path.write_text(
        json.dumps(
            {
                "source_url": source_url,
                "api_docs_url": API_DOCS_URL,
                "fetched_at": fetched_at,
                "locality": slug,
                "year": int(year),
                "filter": {"method": geography_key, geography_key: lsoa_codes},
                "population": total,
                "by_lsoa": sorted(by_lsoa, key=lambda l: l["code"]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote population estimate {total:,} for {slug} ({year}) to {processed_path}")


if __name__ == "__main__":
    main()
