"""
police_crime.py — ingests street-level crime data from the police.uk API,
filtered to a locality's centroid + radius_km.

Why a polygon, not a plain lat/lng query: the API's lat/lng form
(`/crimes-street/all-crime?lat=&lng=`) always returns crimes within a
fixed ~1 mile radius — it ignores any radius you'd want to pass. To honour
a locality's actual `radius_km` from config, this script instead builds a
circular polygon around the centroid and queries the `poly=` form. The
circle is computed with a standard destination-point formula (stdlib
`math` only — no geo library needed for this).

Caching: the API publishes one snapshot per calendar month, immutable once
published. `/api/crime-last-updated` is queried first to find that month,
then the raw response is cached at
  data/raw/police_crime/<slug>/<month>.json
and re-used on subsequent runs for the same month instead of re-fetching.

This script writes the fetched, filtered crime records — nothing derived
from them. Run pipeline/police_crime_stats.py after this to compute
crime_count and anything else derived from the list; see CLAUDE.md rule 1.

Usage:
    python ingest/police_crime.py --config config/salisbury.yml
"""

import argparse
import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

API_BASE = "https://data.police.uk/api"
EARTH_RADIUS_KM = 6371.0088
POLYGON_POINTS = 16


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def circle_polygon(lat: float, lon: float, radius_km: float, points: int = POLYGON_POINTS):
    """Points on a circle of radius_km around (lat, lon), as (lat, lon) pairs."""
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    angular_dist = radius_km / EARTH_RADIUS_KM

    polygon = []
    for i in range(points):
        bearing = math.radians(360 * i / points)
        lat2 = math.asin(
            math.sin(lat1) * math.cos(angular_dist)
            + math.cos(lat1) * math.sin(angular_dist) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angular_dist) * math.cos(lat1),
            math.cos(angular_dist) - math.sin(lat1) * math.sin(lat2),
        )
        polygon.append((math.degrees(lat2), math.degrees(lon2)))
    return polygon


def fetch_json(url: str):
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"police.uk API returned {e.code} for {url}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach police.uk API at {url}: {e.reason}") from e


def latest_available_month() -> str:
    """police.uk returns `date` as YYYY-MM-DD here, but the crimes-street
    `date=` query param takes YYYY-MM — truncate rather than pass through."""
    data = fetch_json(f"{API_BASE}/crime-last-updated")
    return data["date"][:7]


def fetch_crimes(polygon, month: str):
    poly_param = ":".join(f"{lat:.6f},{lon:.6f}" for lat, lon in polygon)
    url = f"{API_BASE}/crimes-street/all-crime?poly={poly_param}&date={month}"
    return fetch_json(url), url


def load_or_fetch_raw(slug: str, polygon, month: str, force: bool):
    raw_dir = Path("data/raw/police_crime") / slug
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{month}.json"

    if raw_path.exists() and not force:
        print(f"Using cached raw pull: {raw_path}")
        cached = json.loads(raw_path.read_text(encoding="utf-8"))
        return cached["crimes"], cached["source_url"], cached["fetched_at"]

    crimes, source_url = fetch_crimes(polygon, month)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_path.write_text(
        json.dumps({"source_url": source_url, "fetched_at": fetched_at, "crimes": crimes}, indent=2),
        encoding="utf-8",
    )
    print(f"Fetched {len(crimes)} crimes, cached to {raw_path}")
    return crimes, source_url, fetched_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    parser.add_argument("--month", default=None, help="YYYY-MM; defaults to the latest month police.uk has published")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached raw pull exists for the month")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("police_crime", {})
    if not source_config.get("enabled"):
        print(f"police_crime is disabled in {args.config} — nothing to do.")
        return

    filter_method = source_config.get("filter_method")
    if filter_method != "radius":
        raise ValueError(
            f"police_crime.filter_method={filter_method!r} isn't implemented — this script only handles 'radius'."
        )

    slug = config["locality"]["slug"]
    geo = config["geography"]
    lat, lon = geo["centroid"]["lat"], geo["centroid"]["lon"]
    radius_km = geo["radius_km"]

    month = args.month or latest_available_month()
    polygon = circle_polygon(lat, lon, radius_km)
    crimes, source_url, fetched_at = load_or_fetch_raw(slug, polygon, month, args.force)

    processed_dir = Path("data/processed") / slug / "police_crime"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / f"{month}.json"
    processed_path.write_text(
        json.dumps(
            {
                "source_url": source_url,
                "api_docs_url": "https://data.police.uk/docs/method/crime-street/",
                "fetched_at": fetched_at,
                "locality": slug,
                "month": month,
                "filter": {"method": "radius", "centroid": {"lat": lat, "lon": lon}, "radius_km": radius_km},
                "crimes": crimes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(crimes)} crimes for {slug} ({month}) to {processed_path}")


if __name__ == "__main__":
    main()
