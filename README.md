# Local Open Data Project — local open data, decoded

A pipeline that pulls public UK datasets, filters them to a single town or
city, and turns the results into short, human-reviewed articles — automated
local data journalism, running entirely on GitHub Pages and GitHub Actions.

Started as a revival of a 2020 Salisbury open data project, rebuilt so the
same pipeline can run for any English or Welsh town by swapping in a new
config file, not by forking the code.

## What it does

1. **Ingests** public data on a schedule — population stats, crime figures,
   company formations, council spending, planning applications.
2. **Filters** everything to a single locality using a shared geography
   pipeline (see "Geography approach" below).
3. **Computes** trends and changes in Python/R — deterministic, no LLM
   involved in the arithmetic.
4. **Drafts** short narrative articles from the *already-computed* numbers,
   using an LLM for phrasing only, never for calculation.
5. **Publishes** to a static site via GitHub Pages, with every figure
   traceable to a source URL and fetch timestamp.

A human reviews and approves before anything publishes. Always.

## Why this is portable

Every locality-specific detail — geography codes, which data sources are
switched on, council-specific file formats, editorial voice — lives in one
config file per place (see `/config/*.yml`). The pipeline code itself
contains no references to any specific town. Adding a second locality means
writing a new config file, not touching the codebase.

The one genuine exception is **council transparency data**, which is
inherently non-standardised across the UK — see "Data sources" below.

## Geography approach: Built-Up Areas, not Local Authorities

The most important design decision in this project: locality boundaries are
based on ONS **Built-Up Areas (BUAs)** — ONS's own settlement boundaries —
rather than Local Authority Districts (LADs) or electoral wards.

This matters because "Salisbury" and "Wiltshire Council" are not the same
thing. Wiltshire is a large unitary authority covering Salisbury,
Trowbridge, Chippenham, Devizes, and a lot of countryside between them.
Filtering national datasets to the LAD alone would produce "Wiltshire
content," not "Salisbury content." Filtering to hand-picked wards works but
requires manual boundary decisions for every new locality. BUAs solve this
properly: ONS has already drawn the actual town boundary, and it's a single
lookup away.

### The ONS lookup join plan

Geography is resolved through a chain of small ONS "best fit" lookup
tables, joined on LSOA and LAD codes, plus one *queried* (not downloaded)
hit against a larger postcode-level product — **never** a full download of
the ONS Postcode Directory (ONSPD) or National Statistics Postcode Lookup
(NSPL), both ~200MB and massive overkill for a single town.

| Step | Source file | Filter / join on | Produces | Approx. size |
|---|---|---|---|---|
| 1 | LSOA (2021) to Built Up Area to LAD to Region lookup (EW) | `BUA22NM` matched to the locality name | `LSOA21CD` list, `LAD22CD` list | ~few MB |
| 2 | LSOA (2021) to Westminster Parliamentary Constituency (best fit) lookup (EW) | `LSOA21CD` from step 1 | Constituency name(s) | ~2.8 MB |
| 3 | Local Authority District to Community Safety Partnership to PFA lookup (EW) | `LAD21CD` from step 1 | Police Force Area name | ~35 KB |
| 4 | LSOA/LAD to Ward best-fit lookup (EW) | `LSOA21CD`/`LAD21CD` from step 1 | Ward name(s) — feeds `local_elections` source | small |
| 5 | LSOA to Rural-Urban Classification lookup (EW) | `LSOA21CD` from step 1 | Dominant rural/urban class | small |
| 6 | National Statistics Postcode Lookup (NSPL), **queried**, not downloaded | `WHERE lsoa21cd IN <list from step 1>` against the hosted ArcGIS feature service | Postcode outward codes | one filtered API call, ~KBs of response |

Step 6 is the fix for what used to be a hand-curated field. NSPL is hosted
on the ONS Open Geography Portal's ArcGIS platform, which supports
server-side attribute queries — sending a `WHERE` clause filtered to a
known LSOA list returns only the matching handful of postcodes, not the
~200MB file. This keeps postcode resolution fully automated without ever
pulling the whole national dataset.

One field is still **deliberately** not derived from any lookup:

- **`centroid`** — a single one-off geocode lookup (e.g. Nominatim, or
  postcodes.io against one representative postcode), not a bulk join. One
  point doesn't need a dataset or a query — just one API call, done once
  per locality.

This whole process is implemented in `generate_locality_geography.py`,
which is a one-off onboarding tool run by hand when adding a new locality —
**not** part of the scheduled ingestion pipeline.

### Coverage limitation: England and Wales only

All three lookup products above are ONS products covering England and
Wales only. Scotland (National Records of Scotland, using Data Zones) and
Northern Ireland (NISRA, using Super Output Areas) have different
statistical geographies from different publishing agencies. Extending this
project to a Scottish or NI locality would need an equivalent-but-different
geography generator script, not just a new config file.

## Data sources

| Source | Coverage | Notes |
|---|---|---|
| ONS population/economic stats | UK-wide | Filtered via `lsoa_codes` (small-area estimates, summed across the BUA — not `local_authority_codes`, which would report the whole council area) |
| Police.uk crime data | England, Wales, NI | Filtered via `centroid` + `radius_km` |
| Companies House | UK-wide | Filtered via `postcode_prefixes` |
| Index of Multiple Deprivation | England only (Wales has a separate, non-comparable WIMD) | Filtered via `lsoa_codes`; a per-LSOA table, not a single locality value — see config comments |
| Local council elections | England/Wales, via Democracy Club | Fetched for the whole council (`council_slug`); the locality's own divisions are selected per election year in `pipeline/`, not via `wards` — see CLAUDE.md. Config: `local_elections` |
| General (parliamentary) elections | England/Wales, via Democracy Club, 2010 onwards | Filtered via `parliamentary_constituencies`. Not the House of Commons Library's 1918-2019 archive — that's Cloudflare-blocked, see CLAUDE.md. Config: `parliamentary_elections` |
| Council transparency (spend-over-£500) | Varies by council | Genuinely non-standardised — see below. Config: `council_transparency` |
| Planning register | Varies by council | Genuinely non-standardised, same as above. Config: `planning_register` (separate source, disabled by default) |
| Community Area JSNA (statutory local intelligence) | Varies by council — this project reads Wiltshire's CAJSNA | Genuinely non-standardised, same category as council transparency — see below. Config: `community_area_jsna` |

Council transparency, planning register, and Community Area JSNA data
are the category where "one pipeline, many localities" breaks down
cleanly — three separate sources in config (`council_transparency`,
`planning_register`, `community_area_jsna`), not one, since a council
can publish any of these independently of the others. Every county or
unitary authority publishes something in each category, but under its
own branding, URL, geography, and format (CSV, PDF, XLSX, interactive
dashboard, with different column names and — for JSNA-style products —
different sub-council geographies entirely). The council-transparency
parser script is meant to be generic — reading a `format` field and a
`column_map` from config — but the specifics of each council's actual
export are captured per-locality in config, not hardcoded. This is also
where document-extraction (PDF table/prose parsing, OCR on scanned
committee papers) does real, previously-manual work.
`ingest/community_area_jsna.py` is a first working example of that
pattern: it downloads and parses Wiltshire's CAJSNA "Summary Data Pack"
PDF (real embedded text, not scanned) for one Community Area, extracting
whichever indicators appear as clean, unambiguous prose sentences and
skipping the rest rather than guessing. Its output is labelled
"<Locality> Community Area" throughout, never the bare locality name —
Wiltshire's Community Area (Area Board) boundary is wider than the
Built-Up Area every other source on this site uses, and conflating the
two would misrepresent the population a figure describes. The parser
itself is Wiltshire-CAJSNA-specific (its indicator sentence patterns are
tied to that document's exact wording), not a generic JSNA parser — a
different council's JSNA would need its own parser script, the same way
`council_transparency` and `planning_register` would. **`council_transparency`
and `planning_register` still don't have ingestion scripts** —
`council_transparency` was investigated and found to need a
headless-browser dependency to get past the target council's Cloudflare
protection (see CLAUDE.md for the full findings); `planning_register` is
config scaffolding only, disabled by default, and hasn't been
investigated at all.

## Running costs

Designed to be a low-single-digit-pounds-per-month project:

- **Compute**: GitHub Actions free tier covers scheduled ingestion jobs
- **Hosting**: GitHub Pages, free
- **LLM spend**: only the narrative-drafting step touches an LLM, and only
  for stats that crossed a significance threshold (see
  `narrative.significance_threshold_pct` in config) — a monthly cadence at
  a few articles keeps this to pennies

## Repo structure

```
/config/                  one YAML file per locality — the portability layer
/data/reference/          cached small ONS lookup tables (BUA, PCON, PFA, LSOA boundaries)
/ingest/                  one script per data source, config-driven — fetches and filters,
                          computes nothing (see CLAUDE.md rule 1)
/pipeline/                stats computation + chart rendering — deterministic, this is
                          where ingested facts become the derived numbers a page shows
/narrative/               LLM-drafted article generation + voice guides
/site/                    static site source
.github/workflows/        scheduled ingestion + build/deploy Actions
generate_locality_geography.py   one-off onboarding script for new localities — see
                          CLAUDE.md for which of its documented steps are actually built
fetch_lsoa_boundaries.py  one-off onboarding script, caches LSOA boundary geometry
                          for choropleth charts
CLAUDE.md                 conventions for Claude Code — read this first
```

## Getting started

1. Download the three ONS lookup files listed above into `/data/reference/`.
2. Run `generate_locality_geography.py` against a Built-Up Area name to
   produce a `geography:` block. **This currently only resolves
   `lsoa_codes`, `local_authority_codes`, `parliamentary_constituencies`,
   and `police_force`** — `wards`, `rural_urban_classification`, and
   `postcode_prefixes` still need hand entry; the script prints TODOs for
   them. See CLAUDE.md for the exact gap.
3. Copy an existing config (e.g. `config/salisbury.yml`) and paste in the
   generated block, plus hand-curated postcode prefixes and a geocoded
   centroid.
4. Fill in the `sources:` block for whichever data sources you're
   switching on for this locality.
5. Run `fetch_lsoa_boundaries.py` if you want choropleth charts for this
   locality (needs `lsoa_codes` from step 2/3 first).
6. Run each source's `ingest/` script by hand, then its `pipeline/`
   companion, and `cd site && npm run build` to check the new locality's
   pages render before pushing. **Nothing runs this automatically yet** —
   `.github/workflows/ingest.yml` is a schedule smoke-test only; it
   doesn't call any ingestion script. Wiring that up is still open work,
   tracked in CLAUDE.md.

## Licensing and attribution

All ingested data is used under the Open Government Licence (OGL) or
equivalent. Every published figure carries its source and fetch date.
