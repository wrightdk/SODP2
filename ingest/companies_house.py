"""
companies_house.py — ingests active/registered companies for a locality,
filtered by `postcode_prefixes`.

Auth: Companies House uses HTTP Basic auth with the API key as the
username and an empty password — read from the COMPANIES_HOUSE_API_KEY
environment variable, never from config or committed to the repo (see
CLAUDE.md's "no secrets in the repo" rule). Get a key at
https://developer.company-information.service.gov.uk (free, API Key
application type).

Why `/advanced-search/companies` with `location=`, not a postcode field:
the API has no dedicated postcode parameter — `location` does a partial
text match against the registered office address, which can include the
postcode. That partial match can false-positive (e.g. "SP1" matching a
street name elsewhere in the address), so results are re-filtered here
to companies whose actual `registered_office_address.postal_code` starts
with the requested prefix before anything is written out.

Caching: the register changes continuously (no natural monthly
snapshot boundary like police.uk), so this follows config's declared
`update_frequency: monthly` as the cache granularity — one raw pull per
calendar month, re-used for the rest of that month.

Usage:
    COMPANIES_HOUSE_API_KEY=... python ingest/companies_house.py --config config/salisbury.yml
"""

import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

API_BASE = "https://api.company-information.service.gov.uk/advanced-search/companies"
API_DOCS_URL = "https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/search/advanced-company-search"
PAGE_SIZE = 500


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_companies_for_prefix(prefix: str, api_key: str):
    """All companies Companies House returns for a location=<prefix> search,
    paginated, filtered to those whose actual postcode starts with prefix."""
    matched = []
    start_index = 0
    request_url = None
    while True:
        params = {"location": prefix, "size": PAGE_SIZE, "start_index": start_index}
        url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
        request_url = request_url or url
        req = urllib.request.Request(url)
        auth = f"{api_key}:".encode("ascii")
        req.add_header("Authorization", "Basic " + base64.b64encode(auth).decode("ascii"))
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"Companies House API returned {e.code} for {url}: {e.read().decode('utf-8', 'replace')}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to reach Companies House API at {url}: {e.reason}") from e

        items = data.get("items", [])
        for item in items:
            postal_code = (item.get("registered_office_address", {}) or {}).get("postal_code", "") or ""
            if postal_code.replace(" ", "").upper().startswith(prefix.replace(" ", "").upper()):
                matched.append(item)

        hits = data.get("hits", 0)
        start_index += PAGE_SIZE
        if start_index >= hits or not items:
            break

    return matched, request_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    parser.add_argument("--month", default=None, help="YYYY-MM; defaults to the current calendar month")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached raw pull exists for the month")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("companies_house", {})
    if not source_config.get("enabled"):
        print(f"companies_house is disabled in {args.config} — nothing to do.")
        return

    filter_by = source_config.get("filter_by")
    if filter_by != "postcode_prefixes":
        raise ValueError(
            f"companies_house.filter_by={filter_by!r} isn't implemented — this script only handles 'postcode_prefixes'."
        )

    api_key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "COMPANIES_HOUSE_API_KEY is not set. Get a free key at "
            "https://developer.company-information.service.gov.uk (API Key application type) "
            "and export it before running this script."
        )

    slug = config["locality"]["slug"]
    prefixes = config["geography"].get("postcode_prefixes")
    if not prefixes:
        raise ValueError("config.geography.postcode_prefixes is empty — nothing to search Companies House with.")

    month = args.month or datetime.now(timezone.utc).strftime("%Y-%m")
    raw_dir = Path("data/raw/companies_house") / slug
    raw_path = raw_dir / f"{month}.json"

    if raw_path.exists() and not args.force:
        print(f"Using cached raw pull: {raw_path}")
        cached = json.loads(raw_path.read_text(encoding="utf-8"))
        companies, source_urls, fetched_at = cached["companies"], cached["source_urls"], cached["fetched_at"]
    else:
        by_number = {}
        source_urls = []
        for prefix in prefixes:
            matched, request_url = fetch_companies_for_prefix(prefix, api_key)
            source_urls.append(request_url)
            for company in matched:
                by_number[company["company_number"]] = company
        companies = list(by_number.values())

        raw_dir.mkdir(parents=True, exist_ok=True)
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_path.write_text(
            json.dumps(
                {"source_urls": source_urls, "fetched_at": fetched_at, "companies": companies}, indent=2
            ),
            encoding="utf-8",
        )
        print(f"Fetched {len(companies)} companies, cached to {raw_path}")

    processed_dir = Path("data/processed") / slug / "companies_house"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / f"{month}.json"

    summarised = [
        {
            "company_name": c.get("company_name"),
            "company_number": c.get("company_number"),
            "company_status": c.get("company_status"),
            "company_type": c.get("company_type"),
            "date_of_creation": c.get("date_of_creation"),
            "date_of_cessation": c.get("date_of_cessation"),
            "postal_code": (c.get("registered_office_address", {}) or {}).get("postal_code"),
        }
        for c in companies
    ]
    active_count = sum(1 for c in summarised if c["company_status"] == "active")

    processed_path.write_text(
        json.dumps(
            {
                "source_url": source_urls[0] if source_urls else None,
                "source_urls": source_urls,
                "api_docs_url": API_DOCS_URL,
                "fetched_at": fetched_at,
                "locality": slug,
                "month": month,
                "filter": {"method": "postcode_prefixes", "postcode_prefixes": prefixes},
                "company_count": len(summarised),
                "active_count": active_count,
                "companies": summarised,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(summarised)} companies ({active_count} active) for {slug} ({month}) to {processed_path}")


if __name__ == "__main__":
    main()
