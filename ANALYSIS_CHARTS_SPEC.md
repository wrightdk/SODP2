# Analysis & charts spec

Chart types worth building per data source, plus the shared infrastructure
that makes several of them cheap once built once. All charts render as
static SVG, generated server-side in the ingestion/analysis pipeline —
not client-side JS — per the project's existing dependency-free principle.

## Shared infrastructure: one choropleth base map

Four sources below want the same thing: colour the 28 Salisbury LSOAs by
some value. Build this once as a shared component, not four times.

- **Boundary geometry**: fetch LSOA boundary shapes from ONS's Open
  Geography Portal, filter to the 28 codes in `lsoa_codes`, cache locally
  (this is a small, filtered pull — same "query/filter, don't bulk
  download" principle as the geography lookups).
- **Renderer**: a single Python function taking `{lsoa_code: value}` and
  a colour scale, returning an SVG. Population density, IMD decile, crime
  rate, and company density all call this with different data.
- **Accessibility**: every choropleth needs an actual legend (not just
  colour), a colourblind-safe sequential palette, and `<title>`/`<desc>`
  in the SVG for screen readers.
- **Tone**: the IMD and crime choropleths in particular are maps of real
  people's neighbourhoods — captions should stay factual and precise
  ("LSOA X falls in decile 2") rather than framing any area as a
  headline or a warning.

## Population

Source: SAPE, LSOA-level (per the recent fix — sums to a real Salisbury
figure, and unlocks age/sex breakdown as a side benefit).

- **Population pyramid** — age bands, male/female, mirrored horizontal
  bars. The classic demographic chart, and SAPE's age/sex breakdown makes
  it free once the LSOA-level source exists.
- **Choropleth: population density** — using the shared base map. Shows
  where within Salisbury people actually live, not just a town total.
- **Trend line: total population over time** — deferred until multiple
  years of SAPE snapshots have accumulated (SAPE is annual, not
  quarterly — see the update_frequency note from the recent fix).

## Police & crime

- **Pie or donut: crime category breakdown** — anti-social-behaviour,
  burglary, violence, etc. as a share of this period's total. The most
  immediately legible chart for this source.
- **Monthly trend by category** — stacked bar or small-multiple line
  charts once enough monthly snapshots exist to show change over time.
- **Choropleth, not a point map, for location** — police.uk deliberately
  anonymises exact locations to an approximate point ("on or near X
  street"), so plotting raw points would visually imply more precision
  than the data actually has. Bucket incidents by LSOA and use the shared
  choropleth instead — more honest about the data's actual resolution.
- **Outcome-recorded rate** — a simple bar showing what share of
  incidents have a recorded outcome vs. still blank. A genuine local-
  accountability angle the raw listing page doesn't surface.

## Companies House

- **Formations vs. dissolutions over time** — a "births and deaths" bar
  chart, the standard way this kind of data gets shown, and intuitive at
  a glance.
- **Sector breakdown** — bar or pie by SIC code category, if the
  ingestion script captures SIC codes (worth checking now, since it's
  much cheaper to capture at ingest time than to backfill later).
- **Choropleth: company density** — using the shared base map, filtered
  by postcode-to-LSOA best-fit. Where in Salisbury business activity
  actually clusters.

## IMD (deprivation)

This was your own example, and it's the strongest case for the shared
choropleth — but a single town-average number undersells it, since IMD
is inherently about variation between neighbourhoods, not one figure.

- **Choropleth: IMD decile across the 28 LSOAs** — the headline visual
  for this source.
- **Distribution bar chart** — how many of the 28 LSOAs fall in each
  national decile (1–10). This is more honest than an average decile,
  since it shows Salisbury actually spans a range rather than being
  uniformly "decile 6."
- **Stretch goal**: IMD's underlying domains (income, employment,
  health, education, crime, barriers to housing, living environment) —
  a per-domain breakdown, if the ingested data captures sub-domain
  scores, not just the composite decile. Worth checking scope before
  committing to this one.

## Council transparency (spend)

- **Top suppliers by total spend** — a horizontal bar of the top 10,
  the classic "who gets the council's money" chart.
- **Monthly spend trend** — a line/bar over time once enough monthly
  snapshots exist.
- **Category breakdown** — pie or bar by service area/spend category,
  if that field exists in Wiltshire's actual export (check the real
  column_map from the council_transparency build before assuming this
  field is there).

## Local elections (future, once the source is built)

- **Vote share by party** — bar chart per ward.
- **Choropleth: winning party by ward** — the classic election result
  map. Now feasible because the `wards` geography field already exists.

## Planning register (future, once the source is built)

- **Applications by status** — bar (approved/refused/pending).
- **Point or choropleth map of application locations**, same anonymity
  consideration as the crime choropleth if location precision is coarse.

## Build order recommendation

1. Shared choropleth base map (unlocks four sources at once)
2. IMD choropleth + distribution bar (data already exists, no new
   ingestion needed — fastest win)
3. Crime pie chart + choropleth (crime data already live)
4. Population pyramid + density choropleth
5. Companies House charts (check SIC code capture first)
6. Council spend charts (check category field availability first)
7. Election/planning charts once those sources exist
