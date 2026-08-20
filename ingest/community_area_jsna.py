"""
community_area_jsna.py — parses Wiltshire's Community Area Joint
Strategic Needs Assessment (CAJSNA) "Summary Data Pack" PDF for one
Community Area, per CLAUDE.md's "Sources that are portable in pattern,
not in specifics": every county/unitary authority publishes a statutory
JSNA, but under its own branding, URL, geography, and format. This
script is written against Wiltshire's specific CAJSNA infographic
template — a different council's JSNA would need its own parser, not a
config tweak to this one.

CRITICAL GEOGRAPHY WARNING: Wiltshire's "Community Area" (this source's
geography — Area Board boundaries: a town plus surrounding villages and
parishes) is NOT the same boundary as the Built-Up Area (BUA) used by
every other source in this project (population, crime, companies, IMD).
A figure from this source describes a wider population than the same
town's BUA-based figures. This script labels every output with
"<area_display_name>" (e.g. "Salisbury Community Area") rather than the
bare locality name specifically to prevent that conflation downstream —
do not simplify that label.

Document structure (confirmed by hand for the Salisbury 2024 pack,
12 pages): page 1 cover, pages 2-5 one infographic per theme (Mental
health / Cost of living / Ageing population / Children and young
people), pages 6-12 a real "Data sources and references" table. Most of
CAJSNA's 140+ indicators live in an interactive dashboard, not this PDF
— this pack only covers the ~4 themes shown in the infographic pages,
and only the indicators below extracted cleanly as unambiguous prose
sentences. Indicators that only appear inside multi-part icon boxes
(e.g. reported missing persons, anti-social behaviour rates), 2-D grid
layouts (e.g. the deprivation-dimensions breakdown, the Universal
Credit employment-status table), or whose reference-table date is
itself ambiguous (e.g. child obesity, cited against three different
NCMP years with no way to tell which the pack's single figure comes
from) were deliberately left out rather than guessed at. This is a
proof-of-concept for the document-parsing pattern on one real example,
not a general-purpose PDF/infographic parser. Extending it to cover the
rest of the pack's stats (icon-box comparisons with reversed value/label
order, 2-D grids, breakdown lists) is real future scope — those layouts
need positional (x, y) extraction via pdfplumber's word coordinates, not
just more regexes over flow text, since their draw order in the PDF
content stream does not reliably match their visual row/column order.

The PDF is genuine embedded text (not a scan — confirmed only 3 image
XObjects across the whole file), extracted with pdfplumber's
`use_text_flow=True`. That flag matters: this pack is laid out as a
multi-column infographic, and pdfplumber's default position-sorted text
order interleaves unrelated columns mid-sentence. `use_text_flow=True`
walks the PDF content stream in the order it was drawn instead, which
matches reading order for this document's layout.

This script performs no computation — every figure below is already a
final percentage/rate in the source PDF; extraction copies it out
verbatim (see CLAUDE.md rule 1). There is no corresponding
pipeline/community_area_jsna_stats.py because there is nothing to
derive.

Usage:
    python ingest/community_area_jsna.py --config config/salisbury.yml
"""

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import yaml

NUM = r"\d+(?:\.\d+)?"


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_pdf(pdf_url: str) -> bytes:
    try:
        with urllib.request.urlopen(pdf_url, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{pdf_url} returned {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach {pdf_url}: {e.reason}") from e


def edition_label(pdf_path: Path) -> str:
    """e.g. 'Wiltshire CAJSNA 2024' -> '2024'; falls back to the filename stem."""
    with pdfplumber.open(pdf_path) as pdf:
        cover_text = pdf.pages[0].extract_text(use_text_flow=True) or ""
    match = re.search(r"CAJSNA\s+(\d{4})", cover_text)
    return match.group(1) if match else pdf_path.stem


def build_patterns(area: str):
    """Regexes are parametrized by the area-board name as it appears in the
    PDF's own prose (config's area_name) — the sentence template itself is
    specific to Wiltshire's CAJSNA pack, not to any one Community Area, so
    this same script works unmodified for another Wiltshire area board's
    PDF (a different config.sources.community_area_jsna.pdf_url + area_name),
    per CLAUDE.md rule 2."""
    return [
        (
            "self_reported_bad_health",
            "Mental health",
            "Population self-reporting bad or very bad health",
            "%",
            rf"In {area}, ({NUM})% of the population perceived themselves to be in bad or very bad health, "
            rf"compared to the county average of ({NUM})% \((\d{{4}})\)",
            ("value", "wiltshire_value", "period"),
            None,
        ),
        (
            "gp_diagnosed_depression",
            "Mental health",
            "Residents registered with a GP with a diagnosis of depression",
            "%",
            rf"In ({NUM}/{NUM}), ({NUM})% of residents in this community area registered with a GP had a "
            rf"diagnosis of depression compared with ({NUM})% in Wiltshire",
            ("period", "value", "wiltshire_value"),
            None,
        ),
        (
            "single_person_households",
            "Mental health",
            "Households that are single-person households",
            "%",
            rf"({NUM})% of households in this community area are single-person households, "
            rf"compared with ({NUM})% across Wiltshire",
            ("value", "wiltshire_value"),
            # No date in the sentence itself — "2021" is confirmed from this
            # indicator's row in the pack's own "Data sources and references"
            # table (Census 2021), not guessed.
            "2021",
        ),
        (
            "fuel_poverty",
            "Cost of living",
            "Homes in fuel poverty",
            "%",
            rf"In (\d{{4}}), ({NUM})% of homes in this area were in fuel poverty, "
            rf"compared with ({NUM})% in Wiltshire",
            ("period", "value", "wiltshire_value"),
            None,
        ),
        (
            "pension_credit_uptake",
            "Cost of living",
            "Pensioners in receipt of Pension Credit",
            "%",
            rf"({NUM})% of pensioners in {area} in (\d{{4}}) received Pension Credit, "
            rf"compared with ({NUM})% in Wiltshire",
            ("value", "period", "wiltshire_value"),
            None,
        ),
        (
            "children_low_income_families",
            "Cost of living",
            "Children under 16 living in a low-income family",
            "%",
            rf"({NUM})% of children aged under 16 in this area in ({NUM}/{NUM}) lived in a low-\s*income family, "
            rf"compared with ({NUM})% across the county",
            ("value", "period", "wiltshire_value"),
            None,
        ),
        (
            "self_reported_good_health_65plus",
            "Ageing population",
            "Residents aged 65 and over self-reporting good health",
            "%",
            rf"In (\d{{4}}), in {area}, ({NUM})% of those aged 65 years and over consider themselves to be in "
            rf"good health, compared with ({NUM})% in Wiltshire",
            ("period", "value", "wiltshire_value"),
            None,
        ),
        (
            "dementia_prevalence",
            "Ageing population",
            "Dementia prevalence",
            "%",
            rf"The prevalence of dementia in this community area was ({NUM})% in ({NUM}/{NUM}), "
            rf"compared to ({NUM})% across Wiltshire",
            ("value", "period", "wiltshire_value"),
            None,
        ),
    ]


def extract_indicators(pdf_path: Path, area: str):
    with pdfplumber.open(pdf_path) as pdf:
        full_text = " ".join(
            re.sub(r"\s+", " ", page.extract_text(use_text_flow=True) or "") for page in pdf.pages
        )

    found, missing = [], []
    for key, theme, label, unit, pattern, field_order, literal_period in build_patterns(area):
        m = re.search(pattern, full_text)
        if not m:
            missing.append(key)
            continue
        values = dict(zip(field_order, m.groups()))
        found.append(
            {
                "key": key,
                "theme": theme,
                "label": label,
                "unit": unit,
                "value": float(values["value"]),
                "wiltshire_value": float(values["wiltshire_value"]),
                "period": literal_period or values["period"],
            }
        )
    return found, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    parser.add_argument("--force", action="store_true", help="Re-fetch the PDF even if this edition is already cached")
    args = parser.parse_args()

    config = load_config(args.config)
    source_config = config.get("sources", {}).get("community_area_jsna", {})
    if not source_config.get("enabled"):
        print(f"community_area_jsna is disabled in {args.config} — nothing to do.")
        return

    pdf_url = source_config["pdf_url"]
    area = source_config["area_name"]
    area_display_name = source_config["area_display_name"]
    slug = config["locality"]["slug"]

    raw_dir = Path("data/raw/community_area_jsna") / slug
    raw_dir.mkdir(parents=True, exist_ok=True)

    # No cheap "what edition is current" endpoint — like ons_population.py,
    # the fetch doubles as the check. Cache under a temp name, then rename
    # once the real edition label is known from the PDF's own cover page.
    tmp_path = raw_dir / "_fetching.pdf"
    existing = sorted(raw_dir.glob("*.pdf"))
    if existing and not args.force:
        pdf_path = existing[-1]
        pdf_fetched_at = datetime.fromtimestamp(pdf_path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"Using cached raw pull: {pdf_path}")
    else:
        pdf_bytes = fetch_pdf(pdf_url)
        tmp_path.write_bytes(pdf_bytes)
        edition = edition_label(tmp_path)
        pdf_path = raw_dir / f"{edition}.pdf"
        tmp_path.rename(pdf_path)
        pdf_fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"Fetched {pdf_url}, cached to {pdf_path}")

    edition = edition_label(pdf_path)
    found, missing = extract_indicators(pdf_path, area)
    if not found:
        raise RuntimeError(f"No indicators extracted from {pdf_path} — check the PDF's layout hasn't changed.")
    if missing:
        print(f"NOTE: {len(missing)} known indicator pattern(s) did not match and were skipped: {missing}")

    # fetched_at (when THIS script ran) is deliberately separate from the
    # report's own edition/period fields — the PDF was published once
    # ("CAJSNA 2024") and each indicator inside it carries its own,
    # earlier data period (e.g. Census 2021, QOF 2022/23); conflating any
    # of these three dates would misrepresent how current the numbers are.
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    processed_dir = Path("data/processed") / slug / "community_area_jsna"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / f"{edition}.json"
    processed_path.write_text(
        json.dumps(
            {
                "source_url": source_config.get("landing_page_url", pdf_url),
                "pdf_url": pdf_url,
                "fetched_at": fetched_at,
                "pdf_fetched_at": pdf_fetched_at,
                "locality": slug,
                "report_edition": f"CAJSNA {edition}",
                "geography": {
                    "label": area_display_name,
                    "caveat": (
                        f"{area_display_name} is Wiltshire Council's Area Board/CAJSNA geography "
                        f"(the town plus surrounding villages and parishes) — a WIDER boundary than "
                        f"the Built-Up Area (BUA) used by every other source on this site. Do not "
                        f"compare or combine these figures with this locality's population, crime, "
                        f"companies, or IMD figures as if they describe the same population."
                    ),
                },
                "indicators_matched": len(found),
                "indicators_skipped": missing,
                "indicators": found,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(found)} CAJSNA indicators for {area_display_name} ({edition}) to {processed_path}")


if __name__ == "__main__":
    main()
