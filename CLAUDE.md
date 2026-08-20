# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state of the repository

The repo skeleton described below now exists (it's a git repo, not yet
pushed to a remote). What's actually built vs. still just scaffolding:

```
config/salisbury.yml                       the only locality config so far
generate_locality_geography.py             onboarding script (v2, "small lookups" approach)
fetch_lsoa_boundaries.py                    one-off cache of LSOA boundary geometry (see below)
data/reference/*.csv, *.xlsx                cached ONS geography lookups
data/reference/lsoa_boundaries_salisbury.geojson  cached LSOA boundaries, for choropleths
data/raw/imd_deprivation/*.xlsx             cached raw IMD file (source for imd_deprivation)
data/raw/{police_crime,ons_population,companies_house}/salisbury/*.json  cached raw API pulls
data/raw/{parliamentary_elections,local_elections}/salisbury/*.json  cached raw Democracy Club pulls
data/processed/salisbury/{police_crime,ons_population,imd_deprivation}/*.json  live sources
data/processed/salisbury/{parliamentary_elections,local_elections}/*.json  live sources
data/processed/salisbury/imd_deprivation/charts/*.svg  pipeline-generated IMD charts
data/processed/salisbury/{parliamentary_elections,local_elections}/charts/*.svg  pipeline-generated
                                            election charts (vote-share line charts + hemicycle)
ingest/{police_crime,ons_population,companies_house,imd_deprivation}.py  fetch + filter
                                            only, no computation (rule 1)
ingest/{parliamentary_elections,local_elections}.py  same rule, both read Democracy Club
pipeline/common.py                         shared read-latest / merge-fields-back-in helpers
pipeline/{police_crime,ons_population,companies_house}_stats.py  compute this source's
                                            derived field(s), merged into ingest/'s output file
pipeline/choropleth.py                     shared, source-agnostic LSOA choropleth renderer
pipeline/imd_charts.py                     IMD-specific: choropleth.py + distribution bar +
                                            average_decile (IMD's stats script, effectively)
pipeline/elections_charts.py               vote-share line chart + hemicycle renderers, shared
                                            across parliamentary_elections and local_elections
.github/workflows/ingest.yml                weekly cron, smoke-test only (see below)
.github/workflows/deploy.yml                builds site/, deploys to Pages via native Pages actions
site/                                        Eleventy site — homepage + Data hub (/data/) +
                                            one page per live source, nested at /data/<slug>/
requirements.txt, .venv/                    see "Environment setup"
narrative/                                  empty (.gitkeep only) — not started
```

`.github/workflows/ingest.yml` runs on a schedule but currently does
nothing but confirm the job executes — it does **not** yet call
`ingest/police_crime.py`. Wiring real ingestion into that workflow is
still open work; don't assume scheduled runs are producing fresh data
until that's done. `.github/workflows/deploy.yml` runs on push to `main`
(and manually via `workflow_dispatch`) and builds `site/` from whatever
`data/processed/` contains at that commit — it does not run ingestion
itself, so a deploy only picks up new data once something else has
committed a fresh `data/processed/` file first. `/pipeline/` and
`/narrative/` have no code in them yet — don't assume they have content;
check before referencing a path there.

`site/src/index.njk` is the real homepage, built from an exported Claude
Design mockup (see DESIGN_HANDOFF_NOTES.md — the four required changes
listed there are implemented). Each live source also has its own detail
page, now living under `site/src/data/` and nested at `/data/<slug>/`
(not `/<source>/` — moved in the same session the Data hub was added):
`data/crime.njk` (`/data/crime/`, still the bare Phase 2 table), plus
`data/population.njk` (`/data/population/`), `data/companies.njk`
(`/data/companies/`), and `data/deprivation.njk` (`/data/deprivation/`)
added in the same session as their ingestion scripts, and
`data/jsna.njk` (`/data/jsna/`). None of these are final page designs
(no "Crime & Safety"-style layout was ever built) — they're all the
same plain pattern: source link, fetched timestamp, a table, and a
"download the raw JSON" link. Each page's `permalink` front matter
reads its URL segment from config (e.g.
`"/data/{{ config.sources.police_crime.slug }}/index.html"`) rather
than hardcoding it, so renaming a source's `slug` in config moves the
page without touching the template. `eleventy.config.js` copies
`data/processed/` to `_site/data/` so those download links resolve to
something real — this sits alongside the page routes under the same
`/data/` URL space without colliding, since page slugs (`crime`,
`population`, …) and the locality slug (`salisbury`) are different
strings; don't pick a source `slug` that collides with a locality slug.
This site deploys to a GitHub Pages *project* subpath (`/SODP2/`, not
the domain root) — `eleventy.config.js` sets `pathPrefix` from a
`PATH_PREFIX` env var (only `deploy.yml`'s CI build sets it; local
build/serve default to `/`), and every internal `href`/`src` in every
template must go through Nunjucks's `| url` filter to pick that up. A
hardcoded `/foo` path works locally and 404s in production — this
already broke the deploy once (see git history), so don't reintroduce
it in a new template.

`site/src/data/index.njk` is the Data hub (`/data/`) — one row per
config source (name, one-line description, licence, last-fetched
timestamp, download link, link through to the source's own page),
built by looping over `config.sources` at build time via
`site/src/_data/dataHub.js`, cross-checked against `data/processed/`
with the same enabled-in-config-AND-file-exists gating as the homepage
cards. **Never hand-add a link to this template** — a source that's
`enabled: true` with a processed file appears automatically; the test
for "is the hub built correctly" is adding a throwaway source to
config + a throwaway file to `data/processed/` and confirming it shows
up with zero template edits (verified this session, then reverted).

`base.njk`'s navbar has one top-level "Data" link, not one link per
source — the five source pages nest under it as a hover/focus dropdown
(`.nav-dropdown` in `styles.css`), so the navbar doesn't grow a new
top-level item every time a source gets a page. The dropdown's own
links still read their `href`s from `config.sources.<key>.slug`, same
as before this restructuring. Adding a page for a new source means
adding an `<a>` inside `.nav-dropdown__menu`, not a new top-level nav
item. The footer keeps the old flat list of links (source, then
per-page links) — footers don't have the same hover affordance as a
navbar, so the clutter concern that motivated the navbar dropdown
doesn't apply there.

Data flows into templates through `site/src/_data/`:
- `config.js` reads whichever `.yml` file it finds first under `/config/`
  — single-locality only for now, see its own comment before assuming it
  handles more than one.
- `homeCards.js` is the card-gating logic: a card only shows a real
  figure if its source is `enabled: true` in config **and**
  `data/processed/<slug>/<source-key>/*.json` exists — otherwise SOON.
  Adding real numbers for a new source means adding a formatter to
  `FIGURE_FORMATTERS` in that file, not just dropping data on disk. A
  card's `page` link is *not* set in `CARD_META` — it's derived from
  `config.sources.<key>.slug` (`null` if the source has no slug yet, same
  as a source with no detail page), the same field `dataHub.js` reads.
- `dataHub.js` builds the Data hub's row list — see above.
- `localities.js`, `populationLocalities.js`, `companiesLocalities.js`,
  and `deprivationLocalities.js` each walk every subdirectory of
  `/data/processed/` for their one source, via the shared
  `site/src/_helpers/sourceData.js` (deliberately outside `_data/` so
  Eleventy doesn't try to load it as its own global data value). None of
  these hardcode "salisbury" even though it's the only locality with data
  today — follow the same pattern for the next source.

**ons_population is now LSOA-level, matching imd_deprivation's pattern**
— it originally summed `local_authority_codes` (Wiltshire's whole
population, 526,392, the same "Wiltshire vs Salisbury" problem the
README calls out as this project's central design decision), fixed to
sum Nomis's small-area estimates (dataset `NM_2014_1`, not `NM_31_1`)
across `lsoa_codes` instead — 47,234 for Salisbury. Small-area estimates
lag district-level ones by about a year (confirmed live: district-level
"latest" was already mid-2025 while small-area "latest" was still
mid-2024) and publish annually, not quarterly — `update_frequency` in
config reflects that now. If a future source needs local-authority-wide
figures on purpose (e.g. something that's genuinely a county-level
statistic), that's a legitimate use of `local_authority_codes` — the
problem was never the field existing, just defaulting to it for a
figure that's supposed to represent the town.

**companies_house.py needs `COMPANIES_HOUSE_API_KEY`** (HTTP Basic auth,
get one free at developer.company-information.service.gov.uk) — verified
live against Salisbury's SP1/SP2 prefixes (10,673 companies, 5,247
active). Keep the key in a local `.env` (already gitignored) and export
it into the shell before running the script — never pass it as a
literal value in a command, since that would put it in shell/session
history.

**`config/salisbury.yml`'s `lsoa_codes` only had 3 of Salisbury's 28
LSOAs** until this session — found while building `imd_deprivation.py`
(a partial list was silently understating the IMD figure: decile 4 from
3 LSOAs vs. the correct decile 7 from all 28). Regenerated from
`generate_locality_geography.py`'s own BUA-matching logic and fixed in
config. If `lsoa_codes` (or `local_authority_codes`) ever look suspiciously
short for a locality, verify against the BUA lookup file rather than
assuming they're complete — `generate_locality_geography.py` itself
currently can't be run end-to-end to double check: `load_police_force()`
opens the PFA lookup with `csv.DictReader`, but that lookup ships as
`.xlsx`, not `.csv` — pre-existing bug, not touched this session since
LAD/LSOA resolution (the part that mattered here) doesn't depend on it.

**No historical snapshots exist anywhere yet** — every source in
`data/processed/` has exactly one file (one month, one year, or one
static release). Checked explicitly for this session since it was
flagged as open in an earlier session. This still doesn't block
choropleth/distribution charts (they're spatial, not time-series — one
snapshot is all either needs), but it does mean **no sparkline or
trend-over-time chart can be built for any source yet**, and nothing in
this session started persisting dated snapshots to make that possible —
that's real scope for whichever session builds the first trend chart
(population pyramid, crime trend line, etc., per
`ANALYSIS_CHARTS_SPEC.md`), not something to assume already exists.

**pipeline/ has its first real content**: `choropleth.py` (generic —
takes `{lsoa_code: value}` + a colour scale, returns an SVG; knows
nothing about IMD or any other source) and `imd_charts.py` (IMD-specific
caller, plus the distribution bar chart, which isn't shared yet — only
the choropleth has a second consumer so far). Reused unchanged by
whichever source's charts get built next per `ANALYSIS_CHARTS_SPEC.md`'s
build order — don't fork `choropleth.py` per source; add a caller module
instead, the same way `imd_charts.py` does.

Rendering is pure Python stdlib — no geopandas/shapely/pyproj. The LSOA
boundaries turned out simple enough (13.5KB for Salisbury's 28 LSOAs,
plain `Polygon`s, ~260 total points) that a real GIS library would have
been a lot of dependency weight for no benefit; `choropleth.py` does its
own equirectangular projection and SVG path generation. Revisit this
choice if a future locality's boundaries turn out far more complex, or a
future chart needs an actual geospatial operation (reprojection, spatial
join) this module doesn't do.

`fetch_lsoa_boundaries.py` (repo root, one-off, same status as
`generate_locality_geography.py` — **not** in `.github/workflows/ingest.yml`)
queries the ONS Open Geography Portal's LSOA (Dec 2021) BSC boundary
FeatureServer, filtered to `config.geography.lsoa_codes`, and caches the
result to `data/reference/lsoa_boundaries_<slug>.geojson`. Re-run it by
hand if a locality's `lsoa_codes` change.

The homepage card mechanism gained a second visual type: `card.chartSvg`
(raw SVG, rendered via `| safe`) alongside the existing `card.hasSpark`
sparkline-polyline mechanism — see `homeCards.js`. IMD's card uses a
compact, legend-less choropleth (`choropleth_mini.svg`) in place of its
old "Decile N" text stat; the full map (with legend) and the distribution
chart are on `/data/deprivation/` only. Both mechanisms read a chart file that
`pipeline/` writes separately from what `ingest/` writes — a card or page
can load before its chart has been generated (rendered as if it just
doesn't have one), so re-run `pipeline/imd_charts.py` after
`ingest/imd_deprivation.py`, not assume one triggers the other.

**council_transparency (Wiltshire spend-over-£500) is investigated but
not built — it's blocked on a real Cloudflare wall, not just unstarted.**
Findings from that investigation, so a future attempt doesn't have to
re-derive them:
- `config/salisbury.yml`'s `spend_over_500_url` was dead (404) — fixed
  to the real page, `https://www.wiltshire.gov.uk/open-data-payments`.
  That page is a listing (one row per month, grouped in per-financial-year
  accordions you have to expand), not a direct file — there's no stable
  URL pattern to construct by hand; each month's download link embeds a
  CMS-assigned numeric ID and a cache-busting timestamp
  (`/media/21219/2026-07-wiltshire-payments/excel/2026-07-wiltshire-payments.csv?m=...`)
  that only appears by rendering the actual page.
- `format: "csv"` in config is confirmed correct — the page mislabels
  the files "Excel doc" but the files themselves are genuinely `.csv`.
  `column_map`'s three field names are still an unverified guess; no file
  was ever successfully downloaded to check real headers against them.
- **The blocker**: wiltshire.gov.uk serves a Cloudflare JS challenge
  ("Just a moment...", Turnstile-based) to non-browser HTTP clients.
  Confirmed directly — `curl` and a plain HTTP GET both get the challenge
  page instead of the CSV, with or without a browser-shaped User-Agent
  header; a real browser (JS execution) gets a 200 for the identical URL.
  This isn't fixable with request headers or `requests`/`urllib` alone.
  Checked for an unprotected mirror too — data.gov.uk/CKAN lists this
  dataset, but its cached resource URLs stop at 2011 and still point back
  to wiltshire.gov.uk regardless, so that's not a working alternative.
- Three ways forward were identified but not decided between: (1) a
  headless-browser dependency (e.g. Playwright) to actually pass the
  challenge — reliable but heavy, ~300MB of browser binaries, and would
  need installing in `.github/workflows/ingest.yml` too; (2) a lighter
  Cloudflare-bypass library (`cloudscraper`, `curl_cffi`) — much smaller,
  but Turnstile-style challenges often defeat these, untested here; (3)
  manual monthly download (same pattern as `imd_deprivation.py` — no
  fetch, just parse whatever's already in `data/raw/`), which sidesteps
  the problem but drops the "actually automated" part of ingestion.
  Whoever picks this up next should decide between those with the user
  rather than silently reaching for one.

Two known gaps from an earlier pass, both flagged rather than silently
patched:
- `config/salisbury.yml`'s `site.hero_image` points at
  `site/src/assets/hero-salisbury.jpg`, which is now in the repo (added
  by hand — the Claude Design MCP's `get_file` truncates anything over
  256 KiB, so the automated fetch of this photo came back incomplete and
  couldn't be used). `hero_image_credit` is filled in with real
  attribution now too.
- `site/src/_includes/base.njk` hardcodes the logo path
  (`/assets/logo-salisbury.jpg`) rather than reading it from config —
  inconsistent with rule 2 below, but out of scope for this session since
  DESIGN_HANDOFF_NOTES.md only called out the hero image fields. Worth
  fixing the same way if a second locality ever gets added.

The ONS reference CSVs/XLSX have already been moved into `/data/reference/`
and the IMD file into `/data/raw/imd_deprivation/` — don't re-download or
duplicate them at the repo root.

**Elections (`local_elections` + `parliamentary_elections`) are now live** —
both read Democracy Club's candidates/results database
(`candidates.democracyclub.org.uk/data/export_csv/`), not the House of
Commons Library's 1918-2019 archive (CBP-8647) the source was originally
briefed against. Findings from building this, so a future session doesn't
re-derive them:

- **commonslibrary.parliament.uk and researchbriefings.files.parliament.uk
  (the direct CSV host) both serve a Cloudflare "Just a moment..." JS
  challenge to non-browser HTTP clients** — confirmed live with curl
  (`cf-mitigated: challenge` in the response headers, browser-shaped
  User-Agent made no difference). Same class of blocker as
  council_transparency's wiltshire.gov.uk wall, not fixable with
  request headers alone. Democracy Club (CloudFront-fronted, not
  Cloudflare) isn't blocked and turned out to cover general elections
  since 2010 too, so `ingest/parliamentary_elections.py` uses it instead
  — plenty for a "last 3 general elections" chart, but if 1918-2019 depth
  is ever actually wanted, that's still blocked and would need the same
  kind of decision council_transparency is waiting on (headless-browser
  dependency vs. manual download vs. something else — ask first).
- Democracy Club's CSV export has no per-constituency or per-council
  query parameter — only a regex against its own `election_id`/
  `ballot_paper_id` scheme. `parliamentary_elections.py` fetches every
  general election candidate nationwide (~20k rows) and filters to
  `geography.parliamentary_constituencies` client-side.
  `local_elections.py` narrows the fetch itself via a new
  `sources.local_elections.council_slug` config field (Democracy Club's
  own council identifier, e.g. `"wiltshire"` — not derivable from
  `council_name` by any reliable slugification rule, so it's stored
  directly, verified live) and double-checks the result's
  `organisation_name` actually matches `council_name` before writing
  anything, in case the slug ever resolves to the wrong council.
- **`config/salisbury.yml`'s `geography.wards` was a fabricated
  placeholder** (already flagged as unverified in an earlier session) —
  it matched *no* real Wiltshire division, old or current boundary.
  Regenerated from Democracy Club's own election data (verified live
  against both the 2021-05-06 and 2025-05-01 elections, which use
  identical division names/codes — a stable current boundary, not a
  one-election snapshot) into the real 8 Salisbury-area divisions. But —
  **`local_elections.py` does NOT filter by `geography.wards`.** Wiltshire's
  division boundaries changed between the 2017 and 2021 elections
  (confirmed live: "Salisbury Harnham" split into "Salisbury Harnham
  East"/"Harnham West" between those two elections, with different GSS
  codes), so a single current `wards` list can't correctly select "this
  locality's divisions" across every election year a multi-year chart
  needs. `ingest/local_elections.py` fetches the *whole council's* data
  instead (needed anyway for the hemicycle — see below), and
  `pipeline/elections_charts.py` selects the locality's own divisions
  per election year by prefix-matching each division's name against
  `geography.bua_name` ("Salisbury ") — verified this correctly finds
  the same 8 divisions in both the 2017 and 2021+ boundary eras. This is
  a "portable in pattern, not in every specific" mechanism (see that
  section below) — a council whose division names don't carry the town
  name as a prefix would need a different selection rule. `wards` is
  kept as the human-readable current list for display purposes, not as
  a filter.
- **The hemicycle chart (current council-wide composition) is
  deliberately NOT "just render the last full election's results"** —
  `pipeline/elections_charts.py`'s `current_composition()` anchors on
  the most recent *ordinary* (non-by-election) election to define the
  current set of seats (excluding boundary-review-superseded divisions
  still present in the history), then takes the most recent result *per
  individual seat* — its anchor result, or a later by-election result if
  one exists — rather than assuming the anchor election is still
  current for every seat. Checked live: Wiltshire has had zero local
  by-elections since the 2025-05-01 full election, so today the two
  approaches happen to produce the same 98-seat composition (37
  Conservative, 43 Liberal Democrats, 7 Independent, 10 Reform UK, 1
  Labour) — that equivalence is real but coincidental to today's date,
  not something the code assumes.
- No new charting dependency was needed for the line charts or the
  hemicycle — both are hand-rolled SVG (stdlib `math`/`colorsys` for the
  hemicycle's row layout and fallback party colours), same approach as
  `choropleth.py`. UK party colours/left-right seating order in
  `pipeline/elections_charts.py`'s `PARTY_STYLES`/`PARTY_LEFT_RIGHT_ORDER`
  follow common public convention, not any officially licensed palette.
- Both sources are now wired into the site (a follow-up session, same
  day): `slug` fields (`local-elections`, `general-elections`) in
  config, `TITLES`/`CARD_META`/`FIGURE_FORMATTERS` entries in
  `dataHub.js`/`homeCards.js`, detail pages at
  `site/src/data/local-elections.njk` and
  `site/src/data/general-elections.njk`, and both added to
  `base.njk`'s nav dropdown and footer. The local-elections homepage
  card reuses the choropleth_mini pattern — a legend-less
  `hemicycle_mini.svg` (`render_hemicycle(..., show_legend=False)`,
  same convention as `choropleth.py`'s `show_legend`) — rather than a
  text figure, since "who controls the council" reads faster as a
  picture than a number. `current_composition()` in
  `elections_charts.py` was refactored to return per-seat dicts
  (`post_label`, `gss`, `party_name`, `election_date`) rather than just
  a flat list of party names, so the same one computation can both
  count seats for the hemicycle *and* slice out this locality's own
  divisions (merged into the processed file as
  `locality_current_divisions`) for the detail page's table — not two
  separate passes over `results` that could drift apart. Party display
  names are also merged into the processed files now
  (`elected_party_short`, `current_composition_largest_party_short`,
  each division's `party_short`) so neither `homeCards.js` nor any
  template needs its own copy of `PARTY_STYLES`' short-label mapping.

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

**Portability/discipline audit (all four findings fixed in this pass):**
A review session read CLAUDE.md, README, and ANALYSIS_CHARTS_SPEC.md
against the actual code across the five sessions since the site was
built, and found real drift in four places. All four are fixed now, but
the *pattern* each fix establishes matters more than the specific fix —
read this before adding a fifth source or a second locality:

1. **Every ingest script computed at least one derived number itself**
   (`imd_deprivation.py`'s `average_decile`, `ons_population.py`'s
   `population` total, `companies_house.py`'s `active_count`,
   `police_crime.py`'s `crime_count`) — rule 1 puts computation in
   `/pipeline/`, and none of it was. Fixed by splitting every source into
   two scripts that both write into the *same* `data/processed/` file:
   `ingest/<source>.py` writes fetched-and-filtered facts only (a list —
   crimes, companies, per-LSOA rows), then `pipeline/<source>_stats.py`
   reads that file and merges the derived field(s) back into it via the
   new `pipeline/common.py` (`latest_processed_path` + `merge_fields`).
   IMD's derived field lives in `pipeline/imd_charts.py` instead of a
   separate `imd_deprivation_stats.py`, since that file already computed
   an equivalent decile breakdown for the distribution chart — before
   this fix, that was two independent computations over the same data in
   two different layers; now there's one. **A source isn't finished
   until both its `ingest/` and `pipeline/` scripts have been run** — the
   site can't show a source's figure from `ingest/` output alone anymore.
   `site/src/_data/homeCards.js`'s formatters check for the specific
   pipeline-written field (e.g. `latest.population === undefined`) and
   return `null` — rendering SOON, not a broken `undefined` — if
   `pipeline/` hasn't run yet; this is what makes the two-step sequence
   safe to get wrong instead of silently showing garbage.
2. **Two different config field names meant the same thing.**
   `ons_population`/`imd_deprivation` used `geography_key` (a pointer to
   *which* `config.geography.*` field to filter by — for sources doing
   simple list-membership); `police_crime`/`companies_house` used
   `filter_by` instead. Unified: `geography_key` is now the only field
   for list-membership filtering (`companies_house` and the not-yet-built
   `local_elections` were switched onto it, since `postcode_prefixes` and
   `wards` are both single-list lookups, same as `lsoa_codes`).
   `police_crime` keeps a separate field, renamed `filter_method` (not
   `geography_key`) — deliberately, since radius filtering needs
   `centroid` *and* `radius_km` together, an algorithm rather than one
   list. **When adding a new source**: if it matches against one
   `geography.*` list, use `geography_key`; only introduce a second
   `filter_method`-style field if the filtering genuinely needs more than
   one geography field or a choice of algorithm — don't default to
   inventing a new field name per source.
3. **`site/src/_includes/base.njk`'s logo path was hardcoded** —
   the one real rule-2 violation the audit found. Fixed the same way
   `hero_image` already was: `config.site.logo` now holds the path,
   templated through `| url` like every other asset reference.
4. **Documentation had drifted from the code in several places** — see
   the README's repo structure tree, data sources table (now two rows
   for `council_transparency`/`planning_register`, since they're
   independent config sources, not one), and "Getting started" (now
   discloses that nothing runs automatically yet, and exactly which
   `generate_locality_geography.py` steps are still manual). Also:
   **a documentation PR from an earlier session (`document-council-
   transparency-cloudflare-blocker`, #7) was opened but never merged** —
   closed instead. Its `config/salisbury.yml` URL fix and column_map
   honesty note were redone directly in this pass since they were still
   correct and still needed; if you find other unmerged-but-still-valid
   work in closed PRs, the same applies — don't assume "closed" always
   means "superseded," check what it actually contained.

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
uv run pipeline/police_crime_stats.py --config config/salisbury.yml   # computes crime_count

# Ingestion: ONS small-area mid-year population estimate (via Nomis), summed across lsoa_codes
uv run ingest/ons_population.py --config config/salisbury.yml
uv run pipeline/ons_population_stats.py --config config/salisbury.yml   # computes population

# Ingestion: Companies House, filtered by geography_key (postcode_prefixes) — needs COMPANIES_HOUSE_API_KEY
COMPANIES_HOUSE_API_KEY=... uv run ingest/companies_house.py --config config/salisbury.yml
uv run pipeline/companies_house_stats.py --config config/salisbury.yml   # computes the counts

# Ingestion: IMD, joined against lsoa_codes — no network call, reads data/raw/imd_deprivation/*.xlsx
uv run ingest/imd_deprivation.py --config config/salisbury.yml

# Ingestion: Wiltshire CAJSNA Summary Data Pack PDF — downloads + parses, no pipeline step (nothing derived)
uv run ingest/community_area_jsna.py --config config/salisbury.yml

# Ingestion: general election results for the constituency, from Democracy Club
uv run ingest/parliamentary_elections.py --config config/salisbury.yml

# Ingestion: local council election results for the whole council, from Democracy Club
# (whole council, not just this locality's divisions — see CLAUDE.md above for why)
uv run ingest/local_elections.py --config config/salisbury.yml

# Onboarding: cache LSOA boundary geometry for choropleths (one-off, like generate_locality_geography.py)
uv run fetch_lsoa_boundaries.py --config config/salisbury.yml

# Pipeline: IMD choropleth + distribution bar charts + average_decile — run after ingest/imd_deprivation.py
uv run pipeline/imd_charts.py --config config/salisbury.yml

# Pipeline: general/local election vote-share line charts + council hemicycle + elected_party/
# current_composition — run after both ingest/parliamentary_elections.py and ingest/local_elections.py
uv run pipeline/elections_charts.py --config config/salisbury.yml

# Site: build the Eleventy site (homepage + one page per live source) from data/processed/
cd site && npm install   # first time only, or after package.json changes
cd site && npm run build # writes site/_site/
cd site && npm run serve # local dev server with live reload
```

`generate_locality_geography.py` takes no other arguments and has no test
coverage — verify its output by hand against the source lookup files when
changing it (and see the PFA-lookup `.xlsx`-read-as-`.csv` bug noted
above if you need `load_police_force()` to actually run). Each ingest
script caches its own way, matching its source's actual update cadence:
`police_crime.py` and `ons_population.py` cache by the resolved
month/year (`--month`/`--year` to override, `--force` to bypass);
`companies_house.py` caches by calendar month per config's declared
`update_frequency` (there's no clean natural snapshot boundary in a
continuously-updated register); `imd_deprivation.py` makes no network
call at all, so there's nothing to cache — it just re-parses the
already-cached `data/raw/imd_deprivation/*.xlsx` every run.

There is no lint or test suite yet. When `/narrative/` gets code, add its
run/test commands here rather than leaving future sessions to guess.

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

6. **Extraction/parsing work reports against an explicit checklist of what
   it should have found, not just a list of what it did find.** Before
   writing extraction code for a source (a PDF, a scraped page, any
   document with a known set of expected fields), enumerate what a
   complete extraction looks like first — then report matches AND misses
   against that list. Silently incomplete output (the script ran, wrote a
   file, and looked done) is a bug, not an acceptable partial result — a
   missing figure needs to be visible as "expected but not found," not
   absent without comment. `ingest/community_area_jsna.py` follows this:
   `build_patterns()` is the checklist, and every pattern that doesn't
   match gets logged to `indicators_skipped` in the output file (and
   printed at run time), rather than just quietly contributing fewer rows
   than expected.

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

## Sources that are portable in pattern, not in specifics

Three known categories exist everywhere in principle but differ in every
actual detail per locality — never assume any of them transfers as-is to a
second locality's config, even though every locality has one:

- **Council transparency data** (spend, planning registers) — every
  council publishes something, but format/columns/URL differ every time.
  See the `council_transparency` investigation above (still blocked on a
  Cloudflare wall for Wiltshire) for how deep that variance goes even
  within one council's own site.
- **Statutory local intelligence / JSNA products** — every county or
  unitary authority produces a Joint Strategic Needs Assessment (a legal
  requirement for Health and Wellbeing Boards), but under its own
  branding, URL, geography, and format. Wiltshire's is
  wiltshireintelligence.org.uk's CAJSNA; other councils will have an
  equivalent that looks nothing like it structurally. Not built yet —
  flagging so a future session doesn't assume Wiltshire's shape
  generalizes.
- **`local_elections`'s locality-division selection.** The source itself
  (Democracy Club's candidates/results database) is genuinely portable —
  same CSV shape, same fields, for every English/Welsh council. What
  isn't portable is `pipeline/elections_charts.py`'s method for picking
  "this locality's divisions" out of a council's full results: it
  prefix-matches division names against `geography.bua_name`, which only
  works because Wiltshire happens to name its Salisbury-area divisions
  "Salisbury <sub-area>". A council that names divisions unrelated to
  the town name (a fairly common pattern too) would need a different
  selection rule — most likely a real LSOA/LAD-to-Ward best-fit lookup
  (join-plan step 4, still not implemented) rather than a name guess.

If you're onboarding a second locality and any of these is already
wired up for the first, budget time to re-verify the URL/file
format/column names/selection rule from scratch — don't assume the
first locality's config values or code are anything more than a
starting guess for the second.

## Target repo structure

See "Current state of the repository" above for what's actually built.
`/config/`, `/data/`, `/ingest/` (partially), `/pipeline/` (just the two
IMD charts so far), `/site/`, and `.github/workflows/` all have real
content now; only `/narrative/` is still empty:

```
/config/                  locality configs — the only place per-town detail lives
/data/reference/           cached ONS lookup tables (small — BUA, PCON, PFA, LSOA boundaries)
/data/raw/                 cached raw API pulls, gitignored or LFS as appropriate
/data/processed/           filtered + computed output (+ pipeline-generated charts), what the site reads from
/ingest/                   one script per data source, all config-driven
/pipeline/                 geography filtering, stats computation, chart rendering — deterministic only
/narrative/                LLM article drafting + per-locality voice guides
/site/                     static site source (11ty — see README)
.github/workflows/         scheduled ingest + build/deploy
generate_locality_geography.py   onboarding tool, run by hand, not scheduled
fetch_lsoa_boundaries.py         onboarding tool, run by hand, not scheduled
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
   optional fields in the README's Data sources table). Include a
   `description` field (one line, shown on the Data hub) — and a `slug`
   field once/if the source gets its own detail page under `/data/`
   (see `site/src/_data/dataHub.js`).
3. Test against at least one existing locality config before considering
   it done — a source that only works for Salisbury isn't finished.
4. Confirm the new source appears automatically on the Data hub
   (`/data/`) after `ingest/` (and `pipeline/`, if it computes a figure)
   run — the hub is built by looping over `config.sources` and checking
   `data/processed/`, so a source with `enabled: true` and a processed
   file should show up with zero template edits. If it doesn't, that's a
   bug in `site/src/_data/dataHub.js`, not a page that needs hand-editing
   — fix the hub rather than adding a one-off entry for the new source.
