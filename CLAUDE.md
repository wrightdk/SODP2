# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state of the repository

The repo skeleton described below now exists (it's a git repo, not yet
pushed to a remote). What's actually built vs. still just scaffolding:

```
config/salisbury.yml                       the only locality config so far
generate_locality_geography.py             onboarding script (v2, "small lookups" approach)
data/reference/*.csv, *.xlsx                cached ONS geography lookups
data/raw/imd_deprivation/*.xlsx             cached raw IMD file (not yet ingested by any script)
data/raw/police_crime/salisbury/*.json      cached raw police.uk pulls, one file per month
data/processed/salisbury/police_crime/*.json  ingested + provenance-tagged output
ingest/police_crime.py                      the only ingestion script written so far
.github/workflows/ingest.yml                weekly cron, smoke-test only (see below)
requirements.txt, .venv/                    see "Environment setup"
pipeline/, narrative/, site/                empty (.gitkeep only) — not started
```

`.github/workflows/ingest.yml` runs on a schedule but currently does
nothing but confirm the job executes — it does **not** yet call
`ingest/police_crime.py`. Wiring real ingestion into that workflow is
still open work; don't assume scheduled runs are producing fresh data
until that's done. `/pipeline/`, `/narrative/`, and `/site/` have no code
in them yet — don't assume any of that scaffolding has content; check
before referencing a path there.

The ONS reference CSVs/XLSX have already been moved into `/data/reference/`
and the IMD file into `/data/raw/imd_deprivation/` — don't re-download or
duplicate them at the repo root.

**Known gap between the documented join plan and the actual script:**
`generate_locality_geography.py` (v2) currently only implements steps 1–3
of the 7-step chain below — BUA→LSOA/LAD, LSOA→PCON, LAD→PFA. It does not
yet do wards (step 4), rural-urban classification (step 5), or the NSPL
query for postcode prefixes (step 6) — those are still TODOs the script
prints out for hand entry. `config/salisbury.yml`'s comment claiming
postcode_prefixes "isn't [manual] anymore" is aspirational, ahead of the
script — don't trust that comment over the script's actual behavior.
Extending the script to cover steps 4–6 is a reasonable next task; when you
do, update both the script's docstring and that config comment together so
they stop disagreeing.

## Environment setup

This project uses **uv** to manage Python, not the system `python3`. On
the machine this was set up on, `/usr/bin/python3` is an old
CommandLineTools build (3.9, LibreSSL 2.8.3) that cannot complete a TLS
handshake with modern APIs like data.police.uk — confirmed directly: a
raw socket handshake to it fails under system Python with
`TLSV1_ALERT_PROTOCOL_VERSION`, while the identical request succeeds via
`curl` or via the uv-managed venv (Python 3.12, OpenSSL 3.5). uv was
chosen over Homebrew because it's a single self-contained install that
manages Python versions itself, rather than needing Homebrew as a
prerequisite first.

**Run project Python through the venv — never bare `python3` / `python`.**
Concretely:

- Prefer `uv run <script> [args]` for one-off invocations — it resolves
  `.venv` automatically with no prior activation needed. This matters
  specifically for an agentic shell: each tool call is a fresh shell, so a
  `source .venv/bin/activate` from one command is **not** still active in
  the next one — relying on activation persisting across separate calls
  silently falls back to system Python instead of erroring.
- Equivalently, call the venv's interpreter directly:
  `.venv/bin/python3 script.py ...`.
- If `.venv/` doesn't exist yet: `uv venv`, then
  `uv pip install -r requirements.txt`.
- `uv` may not be on `PATH` in a tool call's shell even when it is in the
  user's interactive shell — it's typically at `~/.local/bin/uv`. Use the
  full path if a bare `uv` isn't found.

`requirements.txt` is the source of truth for dependencies — once a
package is added there, `uv pip install -r requirements.txt` replaces
one-off `uv pip install <package>` commands, including in setup
instructions given to other contributors.

## Commands

```bash
# Onboarding: resolve a new locality's geography block (prints YAML to stdout)
uv run generate_locality_geography.py \
    --bua-lookup data/reference/<LSOA-BUA-LAD-Region lookup>.csv \
    --pcon-lookup data/reference/<LSOA-PCON lookup>.csv \
    --pfa-lookup data/reference/<LAD-CSP-PFA lookup>.xlsx \
    --bua-name "Salisbury"

# Ingestion: police.uk crime data for one locality, filtered by centroid + radius_km
uv run ingest/police_crime.py --config config/salisbury.yml
```

`generate_locality_geography.py` takes no other arguments and has no test
coverage — verify its output by hand against the source lookup files when
changing it. `ingest/police_crime.py` caches raw pulls under
`data/raw/police_crime/<slug>/<month>.json` and re-uses that cache instead
of re-fetching; pass `--force` to bypass it, `--month YYYY-MM` to fetch a
specific month instead of the latest available.

There is no lint or test suite yet. When `/pipeline/` or `/narrative/` get
code, add their run/test commands here rather than leaving future sessions
to guess.

## The non-negotiable rules

1. **The narrative layer never computes.** LLM calls in `/narrative/` take
   already-computed numbers as input and produce prose. They never derive,
   calculate, estimate, or round a statistic themselves. If a number
   appears in published output, it was computed in Python/R in
   `/pipeline/`, full stop.

2. **Nothing is hardcoded to a specific locality outside `/config/`.**
   Scripts in `/ingest/` and `/pipeline/` read locality parameters from
   the config file passed in; they should run unmodified against any
   locality's config. If you find yourself writing `if locality ==
   "salisbury"` anywhere outside a config file, stop — that logic belongs
   in config.

3. **Geography resolution uses the small ONS lookup tables, not the full
   ONS Postcode Directory (ONSPD).** This was a deliberate decision after
   comparing file sizes — ONSPD is hundreds of MB; the lookup chain below
   is a few MB total. Do not reintroduce an ONSPD dependency without
   discussing it first; it would undo the reason this pipeline stays cheap
   and fast to run in GitHub Actions.

4. **A human reviews before anything publishes.** Never wire the narrative
   step directly to a publish action. The Actions workflow should open a
   PR for review, not push straight to the live site.

5. **`generate_locality_geography.py` is a one-off onboarding tool**, run
   by hand when adding a new locality. It does not belong in the scheduled
   ingestion workflow — don't add it to `.github/workflows/ingest.yml`.

## The ONS geography join plan

This is the exact technical sequence for resolving a locality's geography.
Any ingestion or filtering code touching geography should follow this
chain — don't invent a parallel approach. (Steps 1–3 are implemented in
`generate_locality_geography.py` today; steps 4–6 are documented here but
not yet coded — see "Known gap" above.)

**Goal:** given a place name (a Built-Up Area, e.g. "Salisbury"), produce
the `geography:` block fields in a locality config.

```
Step 1 — LSOA (2021) to Built Up Area to LAD to Region lookup (EW)
  Filter: BUA22NM == <locality name>   (verify BUA22CD is unique for
                                         that name before trusting the
                                         match — some place names recur)
  Yields: LSOA21CD (full list — this becomes `lsoa_codes`)
          LAD22CD  (one or more — becomes `local_authority_codes`, a list,
                    since a BUA can straddle more than one LAD)

Step 2 — LSOA (2021) to Westminster Parliamentary Constituency
          (best fit) lookup (EW)
  Filter: LSOA21CD in <list from step 1>
  Yields: constituency name(s) — becomes `parliamentary_constituencies`
  Note: field name varies by release (PCON24NM / PCON25NM) — detect
        rather than hardcode one.

Step 3 — Local Authority District to Community Safety Partnership
          to PFA lookup (EW)
  Filter: LAD21CD in <LAD list from step 1>
  Yields: PFA21NM — becomes `police_force`
  Note: if this returns more than one force, don't silently pick one —
        surface it, LAD-boundary edge cases are rare but real.

Step 4 — LSOA/LAD to Ward best-fit lookup (EW)
  Filter: LSOA21CD/LAD21CD in <lists from step 1>
  Yields: ward name(s) — becomes `wards`
  Purpose: feeds the `local_elections` source (disabled by default —
  don't enable it in config until the ingestion script actually exists).

Step 5 — LSOA to Rural-Urban Classification lookup (EW)
  Filter: LSOA21CD in <list from step 1>
  Yields: dominant class across the matched LSOAs — becomes
  `rural_urban_classification`. Note this is a locality-level summary
  (majority class), not a per-LSOA list — individual LSOAs at the edge
  of a BUA can differ from the dominant class, which is fine for this
  field's purpose (descriptive colour, not a filter key).

Step 6 — National Statistics Postcode Lookup (NSPL), QUERIED not
          downloaded
  Query: WHERE lsoa21cd IN <list from step 1>, against NSPL's hosted
  ArcGIS feature service on the ONS Open Geography Portal.
  Yields: outward postcode codes — becomes `postcode_prefixes`
  IMPORTANT: this is a server-side filtered API call, not a bulk
  download. NSPL as a full file is ~200MB — do not download it. If you
  find yourself writing code that pulls the whole NSPL file, stop; the
  feature service's query endpoint is the correct approach and this was
  a deliberate design decision, not an oversight.

Step 7 (NOT part of the lookup chain, and never will be) — centroid
  One-off geocode (Nominatim / postcodes.io), a single API call, run by
  a human once per locality. Not a bulk data problem — don't build
  automation for it, don't add it to generate_locality_geography.py.
```

Separately — **Index of Multiple Deprivation (IMD) is not part of this
geography-resolution chain at all.** It's a full per-LSOA data table (a
deprivation decile for each of a locality's LSOAs), so it's implemented as
a source in `/ingest/`, joined against the `lsoa_codes` produced by step 1,
the same way `ons_population` is — not resolved once at onboarding time by
`generate_locality_geography.py`. Don't add an `imd` field under
`geography:` in any locality config; it belongs under `sources:`.

IMD specifically is an England-only product with a different methodology
from Wales's WIMD — the two aren't directly comparable. A Welsh locality's
`imd_deprivation` source config would need to point at WIMD, not IMD.

Reference implementation: `generate_locality_geography.py` at repo root.

Coverage: England and Wales only (see README for why — different
geography systems in Scotland/NI). Don't extend this join plan to those
nations without first checking what the equivalent lookup products are;
they aren't ONS products.

## Target repo structure

See "Current state of the repository" above for what's actually built.
`/config/`, `/data/`, `/ingest/` (partially), and `.github/workflows/`
exist; `/pipeline/`, `/narrative/`, and `/site/` are still empty:

```
/config/                  locality configs — the only place per-town detail lives
/data/reference/           cached ONS lookup tables (small — BUA, PCON, PFA)
/data/raw/                 cached raw API pulls, gitignored or LFS as appropriate
/data/processed/           filtered + computed output, what the site reads from
/ingest/                   one script per data source, all config-driven
/pipeline/                 geography filtering, stats computation — deterministic only
/narrative/                LLM article drafting + per-locality voice guides
/site/                     static site source (11ty/Astro — see README)
.github/workflows/         scheduled ingest + build/deploy
generate_locality_geography.py   onboarding tool, run by hand, not scheduled
```

## Coding conventions

- **Small, reviewable commits/PRs.** One data source or one pipeline stage
  per PR — not a sprawling multi-concern change, even if convenient to
  batch.
- **Config-driven, not conditional.** Prefer adding a config field over
  adding an `if` branch keyed on locality name.
- **Cache raw pulls.** Check `/data/raw/` before re-fetching; respect
  ETag/last-modified where an API supports it. Token and API-call frugality
  is a project value, not an afterthought.
- **Provenance on every figure.** Any number that reaches `/narrative/` or
  the site should carry its source URL and fetch timestamp alongside it.
- **Commit messages**: short imperative summary, e.g. `Add police crime
  ingestion script`, not `Updates`.
- **No secrets in the repo.** API keys via GitHub Actions secrets, never
  committed, never in config YAML.

## When adding a new ingestion source

1. Write the script in `/ingest/`, reading its locality parameters from
   the config file passed as an argument — never from a hardcoded value.
2. Add the source's config block to the schema (document required and
   optional fields in the README's Data sources table).
3. Test against at least one existing locality config before considering
   it done — a source that only works for Salisbury isn't finished.
