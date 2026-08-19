"""
ons_population.py — ingests mid-year population estimates for a locality,
summed across its `local_authority_codes`.

Why Nomis, not api.beta.ons.gov.uk: ONS publishes local-authority-level
population estimates through Nomis (nomisweb.co.uk) — a joint ONS/Durham
University service and the standard, official channel for this exact
granularity of data (free, no registration, JSON/CSV). The newer ONS beta
API doesn't cleanly expose local-authority mid-year estimates at this
level of detail.

Dataset: NM_31_1 ("Population estimates - local authority based by five
year age band"). The query parameter for the sex dimension is `sex`, not
`gender`, despite most Nomis documentation examples using `gender` —
confirmed by trial against the live API; `gender=` silently returns zero
observations rather than an error. `sex=7` is the "Total" (all-persons)
code, `age=0` is "All ages", `measures=20100` is "value" (not percent).

Caching: unlike police.uk, Nomis has no separate cheap "what's the latest
period" endpoint — the actual data query for a locality's total is itself
tiny (a handful of numbers), so that query doubles as the check. The
result's resolved year is used as the cache key; a raw pull already
cached for that year is re-used without hitting the network again.

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

API_BASE = "https://www.nomisweb.co.uk/api/v01/dataset/NM_31_1.data.json"
API_DOCS_URL = "https://www.nomisweb.co.uk/api/v01/about"


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_population(lad_codes, year: str | None):
    params = {
        "geography": ",".join(lad_codes),
        "date": year or "latest",
        "sex": "7",
        "age": "0",
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
    parser.add_argument("--year", default=None, help="Mid-year estimate year, e.g. 2025; defaults to Nomis's latest")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached raw pull exists for the year")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("ons_population", {})
    if not source_config.get("enabled"):
        print(f"ons_population is disabled in {args.config} — nothing to do.")
        return

    geography_key = source_config.get("geography_key", "local_authority_codes")
    lad_codes = config["geography"].get(geography_key)
    if not lad_codes:
        raise ValueError(f"config.geography.{geography_key} is empty — nothing to query Nomis with.")

    slug = config["locality"]["slug"]
    raw_dir = Path("data/raw/ons_population") / slug

    # If --year is given explicitly and already cached, skip the network
    # entirely. Otherwise we don't know the resolved year in advance, so
    # the (tiny) data query doubles as the "what's latest" check — see
    # module docstring.
    cached_path = raw_dir / f"{args.year}.json" if args.year else None
    if cached_path and cached_path.exists() and not args.force:
        print(f"Using cached raw pull: {cached_path}")
        cached = json.loads(cached_path.read_text(encoding="utf-8"))
        write_processed(slug, args.year, cached["obs"], cached["source_url"], cached["fetched_at"], lad_codes, geography_key)
        return

    obs, source_url = fetch_population(lad_codes, args.year)
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

    write_processed(slug, year, obs, source_url, fetched_at, lad_codes, geography_key)


def write_processed(slug, year, obs, source_url, fetched_at, lad_codes, geography_key):
    by_authority = [
        {
            "code": o["geography"]["value"],
            "name": o["geography"]["description"],
            "population": o["obs_value"]["value"],
        }
        for o in obs
    ]
    total = sum(a["population"] for a in by_authority)

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
                "filter": {"method": geography_key, geography_key: lad_codes},
                "population": total,
                "by_authority": by_authority,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote population estimate {total:,} for {slug} ({year}) to {processed_path}")


if __name__ == "__main__":
    main()
