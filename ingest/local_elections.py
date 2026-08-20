"""
local_elections.py — ingests local council election results for a
locality's council, filtered by config's `council_slug`.

Source: Democracy Club's candidates/results database (same provider as
parliamentary_elections.py — see that script's docstring for why this
project uses Democracy Club rather than council-specific sources here).
Coverage: local elections since 2016, by-elections since May 2017.

This writes the WHOLE council's results, not narrowed to this
locality's wards/divisions — deliberately. Two reasons:

1. The hemicycle chart (pipeline/elections_charts.py) needs the current
   holder of every seat on the council, not just the locality's own
   seats, to show the council's overall party composition.
2. The locality's own division names and GSS codes changed between the
   2017 and 2021 elections (Wiltshire had a boundary review — confirmed
   live: "Salisbury Harnham" split into "Salisbury Harnham East"/"Harnham
   West" between those two elections, both with different GSS codes). A
   single current `geography.wards` list can't correctly select "this
   locality's divisions" across every election year on its own — see
   config/salisbury.yml's `local_elections` comment. Keeping the whole
   council's data lets pipeline/elections_charts.py apply a
   boundary-era-aware selection (name-prefix match, per election year)
   itself, rather than baking a wrong selection in at ingest time.

Why `council_slug`, not `council_name`: Democracy Club's CSV export has
no organisation-name query parameter — only a regex against its own
`election_id`/`ballot_paper_id` scheme (e.g.
"local.<council_slug>.<division>.<date>"), so the slug has to be known
ahead of time (config/salisbury.yml's comment on this field explains
where it came from). `council_name` is still used here as a live
sanity check: if none of the fetched rows' `organisation_name` matches
it, the slug has resolved to the wrong council and this script stops
rather than silently writing another council's results.

Caching: like companies_house.py, there's no natural per-election
snapshot boundary from this script's point of view (it always asks for
"this council's whole election history so far"), so this follows the
same calendar-month cache granularity — one raw pull per month, reused
for the rest of that month, `--force` to bypass. A new by-election
becomes visible after the next monthly cache expiry (or --force) — this
matters more here than for parliamentary_elections, since the whole
point of the hemicycle chart is picking up by-elections promptly.

This script writes the fetched, filtered candidate rows only — nothing
derived (no vote shares, no per-seat "who currently holds this"). Run
pipeline/elections_charts.py after this; see CLAUDE.md rule 1.

Usage:
    python ingest/local_elections.py --config config/salisbury.yml
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

KEPT_FIELDS = [
    "election_date",
    "post_label",
    "gss",
    "party_name",
    "party_id",
    "person_name",
    "votes_cast",
    "elected",
    "rank",
    "by_election",
    "cancelled_poll",
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
    (results alone omits organisation_name/post_label context fields)."""
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


def load_or_fetch_raw(slug: str, council_slug: str, month: str, force: bool):
    raw_dir = Path("data/raw/local_elections") / slug
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{month}.json"

    if raw_path.exists() and not force:
        print(f"Using cached raw pull: {raw_path}")
        cached = json.loads(raw_path.read_text(encoding="utf-8"))
        return cached["rows"], cached["source_url"], cached["fetched_at"]

    params = [
        ("election_date", ""),
        ("election_id", f"^local\\.{council_slug}\\..*"),
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
    print(f"Fetched {len(rows)} candidate rows for council_slug={council_slug!r}, cached to {raw_path}")
    return rows, source_url, fetched_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    parser.add_argument("--month", default=None, help="YYYY-MM; defaults to the current calendar month")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached raw pull exists for the month")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("local_elections", {})
    if not source_config.get("enabled"):
        print(f"local_elections is disabled in {args.config} — nothing to do.")
        return

    council_slug = source_config.get("council_slug")
    council_name = source_config.get("council_name")
    if not council_slug:
        raise ValueError("sources.local_elections.council_slug is not set in config — see its comment for what this needs to be.")

    slug = config["locality"]["slug"]
    month = args.month or datetime.now(timezone.utc).strftime("%Y-%m")
    rows, source_url, fetched_at = load_or_fetch_raw(slug, council_slug, month, args.force)

    if not rows:
        raise RuntimeError(f"No rows returned for council_slug={council_slug!r} — check the slug is still correct.")

    orgs_seen = {r.get("organisation_name") for r in rows}
    if council_name and council_name not in orgs_seen:
        raise RuntimeError(
            f"council_slug={council_slug!r} returned organisation_name(s) {sorted(orgs_seen)}, "
            f"none of which match council_name={council_name!r} — the slug may have resolved to the wrong council."
        )

    matched = [{field: row.get(field) for field in KEPT_FIELDS} for row in rows]
    election_dates = sorted(set(r["election_date"] for r in matched))
    division_count = len(set(r["post_label"] for r in matched))
    print(f"Matched {len(matched)} candidate rows across {len(election_dates)} elections and {division_count} divisions.")

    processed_dir = Path("data/processed") / slug / "local_elections"
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
                "filter": {"method": "council_slug", "council_slug": council_slug, "council_name": council_name},
                "election_dates": election_dates,
                "results": sorted(matched, key=lambda r: (r["election_date"], r["post_label"], -int(r["votes_cast"] or 0))),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(matched)} candidate rows for {slug} ({month}) to {processed_path}")


if __name__ == "__main__":
    main()
