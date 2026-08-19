"""
generate_locality_geography.py  (v2 — small-lookups approach)

Derives the `geography:` block of a locality config from a Built-Up Area
(BUA) name, using a stack of small ONS "best fit" lookup tables joined on
LSOA/LAD codes — NOT the full ONS Postcode Directory. Total download size
for all three lookups is a few MB, versus hundreds of MB for ONSPD.

Why BUA rather than LAD or ward:
  BUAs are ONS's own settlement boundaries — "Salisbury" as a place, not
  as an administrative unit. This gives town-level precision without the
  ward-by-ward hand-curation the earlier draft of this script needed, and
  without the "whole of Wiltshire" over-reach of filtering by LAD alone.

Coverage: England and Wales only (these ONS products don't extend to
Scotland or Northern Ireland, which use separate statistical geographies
— Data Zones and SOAs respectively — published by different agencies).
Fine for an England-focused locality, but worth knowing if this project
ever extends beyond E&W.

Required input files (download once, cache, reuse for every locality):

  1. LSOA (2021) to Built Up Area to LAD to Region lookup (EW)
     — the file already in this project.
  2. LSOA (2021) to Westminster Parliamentary Constituency (best fit) lookup (EW)
     — ~2.8MB, from the ONS Open Geography Portal.
  3. Local Authority District to Community Safety Partnership to PFA lookup (EW)
     — ~35KB, from the same portal.

Postcode prefixes and centroid are NOT derived from these files — see
notes at the bottom of this script.

Usage:
    python generate_locality_geography.py \
        --bua-lookup data/reference/lsoa_bua_lad_region.csv \
        --pcon-lookup data/reference/lsoa_pcon_lad.csv \
        --pfa-lookup data/reference/lad_csp_pfa.csv \
        --bua-name "Salisbury"
"""

import argparse
import csv
from collections import Counter
from pathlib import Path


def load_bua_rows(bua_path: Path, bua_name: str):
    """Return (lsoa_codes, lad_codes) for the given BUA name.
    Matches on name but verifies a single underlying BUA code — some place
    names recur across England and Wales, so a name match alone isn't
    trustworthy without this check."""
    lsoa_codes = set()
    lad_codes = Counter()
    bua_codes_seen = set()

    with open(bua_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["BUA22NM"].strip().lower() != bua_name.strip().lower():
                continue
            bua_codes_seen.add(row["BUA22CD"])
            lsoa_codes.add(row["LSOA21CD"])
            lad_codes[row["LAD22CD"]] += 1

    if not lsoa_codes:
        raise ValueError(f"No BUA match for '{bua_name}' — check exact ONS naming.")
    if len(bua_codes_seen) > 1:
        raise ValueError(
            f"'{bua_name}' matches multiple distinct BUA codes ({bua_codes_seen}) — "
            f"this name isn't unique in the file, re-match on BUA22CD instead."
        )
    if len(lad_codes) > 1:
        print(f"NOTE: '{bua_name}' spans more than one LAD: {dict(lad_codes)}. "
              f"This happens at LAD boundaries — both will be included.")

    return lsoa_codes, set(lad_codes.keys())


def load_constituencies(pcon_path: Path, lsoa_codes: set) -> set:
    constituencies = set()
    with open(pcon_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Field name varies slightly by release (PCON24NM vs PCON25NM) —
        # detect whichever is present rather than hardcoding one.
        fieldnames = reader.fieldnames
        pcon_field = next((c for c in fieldnames if c.startswith("PCON") and c.endswith("NM")), None)
        if pcon_field is None:
            raise ValueError(f"No PCON name column found in {pcon_path}; columns were {fieldnames}")

        for row in reader:
            if row["LSOA21CD"] in lsoa_codes:
                constituencies.add(row[pcon_field])
    return constituencies


def load_police_force(pfa_path: Path, lad_codes: set) -> set:
    forces = set()
    with open(pfa_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["LAD21CD"] in lad_codes:
                forces.add(row["PFA21NM"])
    return forces


def to_yaml_block(lsoa_codes, lad_codes, constituencies, forces,
                   postcode_prefixes=None, centroid=None, radius_km=None) -> str:
    lines = ["geography:"]
    lines.append("  local_authority_codes:")
    lines += [f"    - \"{c}\"" for c in sorted(lad_codes)]
    lines.append("  lsoa_codes:")
    lines += [f"    - \"{l}\"" for l in sorted(lsoa_codes)]
    lines.append("  parliamentary_constituencies:")
    lines += [f"    - \"{c}\"" for c in sorted(constituencies)]
    lines.append("  police_force:" + (f" \"{sorted(forces)[0]}\"" if len(forces) == 1 else ""))
    if len(forces) > 1:
        lines += [f"    # WARNING multiple forces matched: {sorted(forces)} — verify manually"]
    lines.append("  postcode_prefixes:  # hand-curate — no small ONS lookup covers this")
    if postcode_prefixes:
        lines += [f"    - \"{p}\"" for p in postcode_prefixes]
    else:
        lines.append("    - \"\"  # TODO: fill in, e.g. SP1, SP2")
    lines.append("  centroid:  # from a one-off geocode, not derived here")
    lines.append(f"    lat: {centroid[0] if centroid else '0.0  # TODO'}")
    lines.append(f"    lon: {centroid[1] if centroid else '0.0  # TODO'}")
    lines.append(f"  radius_km: {radius_km if radius_km else '0  # TODO: set manually'}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bua-lookup", required=True, type=Path)
    parser.add_argument("--pcon-lookup", required=True, type=Path)
    parser.add_argument("--pfa-lookup", required=True, type=Path)
    parser.add_argument("--bua-name", required=True)
    parser.add_argument("--postcode-prefixes", default=None,
                         help="Comma-separated, hand-curated, e.g. 'SP1,SP2'")
    args = parser.parse_args()

    lsoas, lads = load_bua_rows(args.bua_lookup, args.bua_name)
    constituencies = load_constituencies(args.pcon_lookup, lsoas)
    forces = load_police_force(args.pfa_lookup, lads)
    prefixes = [p.strip() for p in args.postcode_prefixes.split(",")] if args.postcode_prefixes else None

    print(to_yaml_block(lsoas, lads, constituencies, forces, postcode_prefixes=prefixes))

# ----------------------------------------------------------------------
# NOTES ON THE TWO FIELDS THIS SCRIPT DELIBERATELY DOESN'T AUTOMATE:
#
# postcode_prefixes — no small official ONS "best fit" product maps BUAs
# to postcode districts. Options, in order of effort: (1) hand-type them,
# genuinely reasonable for one or two districts you already know; (2) use
# a free lookup tool (e.g. doogal.co.uk) to pull postcodes filtered to a
# specific outward code, if you need to confirm boundaries rather than
# just knowing them offhand; (3) only fall back to a full ONSPD/NSPL
# download if a locality's postcode geography turns out to be genuinely
# unclear to a local.
#
# centroid — a single geocode API call (Nominatim, or postcodes.io given
# one representative postcode) for the town name is a one-off lookup, not
# a bulk data problem, so it doesn't belong in this ONS-lookup-based
# script. Run it separately and paste the result in.
# ----------------------------------------------------------------------
