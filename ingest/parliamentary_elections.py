"""
parliamentary_elections.py — ingests UK general election results for a
locality's Westminster constituency, filtered by config's
`geography_key` (parliamentary_constituencies).

Source: Democracy Club's candidates/results database, not the House of
Commons Library's 1918-2019 archive (CBP-8647) the original brief for
this source named. Both commonslibrary.parliament.uk and
researchbriefings.files.parliament.uk (the direct CSV host) serve a
Cloudflare "Just a moment..." JS challenge to non-browser HTTP clients —
confirmed live with curl (browser-shaped User-Agent, `cf-mitigated:
challenge` in the response headers), the same class of blocker
CLAUDE.md already documents for council_transparency's wiltshire.gov.uk
wall. Democracy Club's export_csv endpoint (candidates.democracyclub.org.uk,
CloudFront-fronted, not Cloudflare) is not blocked. Its coverage is
general elections since 2010 (2010/2015/2017/2019/2024 — five
elections) — enough for a "last 3" chart, but not the House of Commons
Library's full 1918 depth. If 1918-2019 depth is ever actually needed,
that requires either a headless-browser dependency to pass the
Cloudflare challenge, or a manual-download workflow (same shape as
council_transparency's unresolved options) — not attempted here.

Why the whole "parl." dataset is fetched, not just this constituency:
Democracy Club's export_csv only filters server-side by a regex against
`election_id` (the UK-wide parent election, e.g. "parl.2024-07-04"), not
by `post_label` (the per-constituency ballot) — there's no per-constituency
query parameter. So this script fetches every constituency's results for
every general election since 2010 (~20,000 candidate rows, ~20MB
pretty-printed) and filters to this locality's constituency/
constituencies client-side before writing anything out — the same
"fetch broad, write filtered" shape as imd_deprivation.py filtering a
whole England-wide workbook down to lsoa_codes. Unlike that workbook,
this is a genuinely nationwide, not-locality-specific pull, so the raw
cache (~20MB) is duplicated in full per locality
(data/raw/parliamentary_elections/<slug>/) rather than shared — there's
no cross-locality cache reuse anywhere else in this codebase either
(every ingest script runs against one config at a time), so this
matches the existing per-locality-cache convention rather than
inventing a new shared-cache mechanism; a second locality onboarding
will re-download and re-commit its own ~20MB copy. Worth revisiting if
this project ever onboards many localities at once.

Caching: like companies_house.py, there's no natural per-election
snapshot boundary to key a cache on from this script's point of view (it
always asks for "every general election so far"), so this follows the
same calendar-month cache granularity — one raw pull per month, reused
for the rest of that month, `--force` to bypass. A new general election
becomes visible after the next monthly cache expiry (or --force), not
immediately.

This script writes the filtered, general-elections-only candidate rows —
nothing derived (no vote shares, no "who won"). Run
pipeline/elections_charts.py after this, which computes vote share and
renders the general-election line chart; see CLAUDE.md rule 1.

Usage:
    python ingest/parliamentary_elections.py --config config/salisbury.yml
"""

import argparse
import csv
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

EXPORT_CSV_URL = "https://candidates.democracyclub.org.uk/data/export_csv/"
API_DOCS_URL = "https://developers.democracyclub.org.uk/api/v1/"
# Every candidate row from every UK general election since 2010 —
# by_election is filtered client-side below (Westminster by-elections
# share the "parl." prefix but aren't "general election results").
ELECTION_ID_PATTERN = r"^parl\..*"

# Fields kept from Democracy Club's export — trimmed from its full
# column set (person_id, ballot_paper_id, gss, nuts1, candidates_locked,
# etc. dropped) to what a vote-share chart and a "who's the current MP"
# stat actually need, plus results_source for provenance.
KEPT_FIELDS = [
    "election_date",
    "post_label",
    "party_name",
    "party_id",
    "person_name",
    "votes_cast",
    "elected",
    "rank",
    "turnout_percentage",
    "total_electorate",
    "results_source",
]


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_csv_rows(params):
    """params: a list of (key, value) tuples — a plain dict can't express
    the repeated `field_group=results&field_group=election` this needs
    (results alone omits post_label, the field this filters on)."""
    url = f"{EXPORT_CSV_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "SODP2 (github.com/wrightdk/SODP2)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Democracy Club export_csv returned {e.code} for {url}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach Democracy Club export_csv at {url}: {e.reason}") from e

    rows = list(csv.DictReader(io.StringIO(body)))
    return rows, url


def load_or_fetch_raw(slug: str, month: str, force: bool):
    raw_dir = Path("data/raw/parliamentary_elections") / slug
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{month}.json"

    if raw_path.exists() and not force:
        print(f"Using cached raw pull: {raw_path}")
        cached = json.loads(raw_path.read_text(encoding="utf-8"))
        return cached["rows"], cached["source_url"], cached["fetched_at"]

    params = [
        ("election_date", ""),
        ("election_id", ELECTION_ID_PATTERN),
        ("format", "csv"),
        ("field_group", "results"),
        ("field_group", "election"),
    ]
    rows, source_url = fetch_csv_rows(params)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_path.write_text(
        json.dumps({"source_url": source_url, "fetched_at": fetched_at, "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print(f"Fetched {len(rows)} UK-wide general election candidate rows, cached to {raw_path}")
    return rows, source_url, fetched_at


def is_general_election_row(row: dict) -> bool:
    return row.get("by_election", "").strip().lower() not in ("t", "true")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    parser.add_argument("--month", default=None, help="YYYY-MM; defaults to the current calendar month")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached raw pull exists for the month")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("parliamentary_elections", {})
    if not source_config.get("enabled"):
        print(f"parliamentary_elections is disabled in {args.config} — nothing to do.")
        return

    slug = config["locality"]["slug"]
    geography_key = source_config.get("geography_key", "parliamentary_constituencies")
    constituencies = config["geography"].get(geography_key)
    if not constituencies:
        raise ValueError(f"config.geography.{geography_key} is empty — nothing to filter general election results by.")

    month = args.month or datetime.now(timezone.utc).strftime("%Y-%m")
    all_rows, source_url, fetched_at = load_or_fetch_raw(slug, month, args.force)

    constituency_set = set(constituencies)
    matched = [
        {field: row.get(field) for field in KEPT_FIELDS}
        for row in all_rows
        if is_general_election_row(row) and row.get("post_label") in constituency_set
    ]
    if not matched:
        raise RuntimeError(
            f"None of config.geography.{geography_key} ({constituencies!r}) matched any post_label "
            f"in Democracy Club's general election data — check the constituency name is current."
        )

    matched_dates = sorted(set(r["election_date"] for r in matched))
    missing_constituencies = constituency_set - {r["post_label"] for r in matched}
    if missing_constituencies:
        print(f"WARNING: no results found at all for: {sorted(missing_constituencies)}")
    print(f"Matched {len(matched)} candidate rows across {len(matched_dates)} general elections: {matched_dates}")

    processed_dir = Path("data/processed") / slug / "parliamentary_elections"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / f"{month}.json"
    processed_path.write_text(
        json.dumps(
            {
                "source_url": source_url,
                "api_docs_url": API_DOCS_URL,
                "fetched_at": fetched_at,
                "locality": slug,
                "month": month,
                "filter": {"method": geography_key, geography_key: constituencies, "by_election": False},
                "election_dates": matched_dates,
                "results": sorted(matched, key=lambda r: (r["election_date"], -int(r["votes_cast"] or 0))),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(matched)} general election candidate rows for {slug} ({month}) to {processed_path}")


if __name__ == "__main__":
    main()
