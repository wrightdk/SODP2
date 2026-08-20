// Homepage data-source cards, gated per DESIGN_HANDOFF_NOTES.md point 1:
// a card only shows real numbers if its source is `enabled: true` in
// config AND a processed file actually exists for it — otherwise it
// renders the SOON state. Card titles/descriptions are generic per
// source (not locality-specific), so this works unmodified for any
// locality config.
const path = require("path");
const loadConfig = require("./config.js");
const { latestFile, readChartSvg } = require("../_helpers/sourceData.js");

const DATA_ROOT = path.join(__dirname, "../../../data/processed");

// `page` is not listed here — it's derived per-source from config's
// `slug` field (site/src/_data/dataHub.js reads the same field), not
// hardcoded per source. A source with no `slug` in config has no page
// yet and its card renders SOON-only, even once it has data.
const CARD_META = {
  ons_population: {
    title: "Population & Economy",
    // LSOA-level (summed across the BUA's actual LSOA membership), not
    // local-authority-level — this used to report Wiltshire's population
    // (~500k) instead of Salisbury's. See CLAUDE.md.
    desc: (c) => `ONS small-area mid-year population estimate summed across ${c.locality.name}'s ${(c.geography.lsoa_codes || []).length} LSOAs.`,
  },
  police_crime: {
    title: "Police & Crime",
    desc: (c) => `Monthly incident counts from police.uk, filtered to a ${c.geography.radius_km}km radius of central ${c.locality.name}.`,
  },
  companies_house: {
    title: "Companies & Business",
    desc: (c) => `Active companies with a registered office in the ${(c.geography.postcode_prefixes || []).join("/")} postcode area, via Companies House.`,
  },
  council_transparency: {
    title: "Council Spending",
    desc: (c) => `Payments over £500 published by ${c.sources.council_transparency.council_name} under the transparency code.`,
  },
  planning_register: {
    title: "Planning Register",
    desc: (c) => `Planning applications from ${c.sources.council_transparency ? c.sources.council_transparency.council_name : "the council"}'s register.`,
  },
  imd_deprivation: {
    title: "Deprivation (IMD)",
    desc: (c) => `English Indices of Deprivation, joined per Lower-layer Super Output Area across ${c.locality.name}'s ${(c.geography.lsoa_codes || []).length} LSOAs.`,
  },
  local_elections: {
    title: "Local Elections",
    desc: (c) => `${c.sources.local_elections.council_name}'s current party composition, from Democracy Club.`,
  },
  parliamentary_elections: {
    title: "General Elections",
    desc: (c) => `General election results for ${c.locality.name}'s constituency, from Democracy Club.`,
  },
  // NOTE: this source's geography is the Community Area (Area Board
  // boundary — wider than the BUA every other card uses), never just
  // "<locality name>" — see CLAUDE.md and ingest/community_area_jsna.py.
  community_area_jsna: {
    title: "Community Area JSNA",
    desc: (c) =>
      `Selected indicators from Wiltshire Council's statutory Community Area JSNA for the ${c.sources.community_area_jsna ? c.sources.community_area_jsna.area_display_name : "Community Area"} — a wider boundary than ${c.locality.name}'s Built-Up Area used elsewhere on this site.`,
  },
};

// Sources with a formatter here can render real numbers once they have
// enabled:true + processed data; sources without one always show SOON,
// even if data later appears, until someone teaches this file how to
// read that source's output shape. Formatters take (latest, slug) —
// slug is only used by sources with a chart to read (see imd_deprivation
// below); everything else ignores it. None of these have a time-series
// sparkline yet — each source is a single snapshot (one month or one
// static release), not a time series. See DESIGN_HANDOFF_NOTES.md point 4.
//
// Every field a formatter reads here is written by a pipeline/ script,
// not ingest/ (see CLAUDE.md rule 1) — ingest/ and pipeline/ run as
// separate steps, so a formatter must return null if pipeline/ hasn't
// run yet rather than render "undefined". A card that's missing its
// computed stat shows SOON, the same as a card with no data at all —
// never a broken-looking number.
const FIGURE_FORMATTERS = {
  police_crime: (latest) => {
    if (latest.crime_count === undefined) return null; // pipeline/police_crime_stats.py hasn't run
    return {
      figure: String(latest.crime_count),
      unit: `incidents, ${latest.month}`,
      hasSpark: false,
      fetchedAt: latest.fetched_at,
      updateLabel: `${latest.month} incidents`,
    };
  },
  ons_population: (latest) => {
    if (latest.population === undefined) return null; // pipeline/ons_population_stats.py hasn't run
    return {
      figure: latest.population.toLocaleString("en-GB"),
      unit: `residents, mid-${latest.year}`,
      hasSpark: false,
      fetchedAt: latest.fetched_at,
      updateLabel: `mid-${latest.year} population estimate`,
    };
  },
  companies_house: (latest) => {
    if (latest.active_count === undefined) return null; // pipeline/companies_house_stats.py hasn't run
    return {
      figure: String(latest.active_count),
      unit: "active companies",
      hasSpark: false,
      fetchedAt: latest.fetched_at,
      updateLabel: `${latest.month} companies register`,
    };
  },
  // Replaces the plain "Decile N" text stat with the compact choropleth
  // from pipeline/imd_charts.py, per this session's scope — the card
  // links to /deprivation/ for the full map (with legend) and the
  // distribution chart. Falls back to the text figure if the chart
  // hasn't been generated yet (pipeline/ runs separately from ingest/).
  imd_deprivation: (latest, slug) => {
    if (latest.average_decile === undefined) return null; // pipeline/imd_charts.py hasn't run
    const chartSvg = readChartSvg(DATA_ROOT, slug, "imd_deprivation", "choropleth_mini");
    return {
      figure: chartSvg ? null : `Decile ${latest.average_decile}`,
      chartSvg,
      unit: `Decile ${latest.average_decile} · IMD, ${latest.release}`,
      hasSpark: false,
      fetchedAt: latest.fetched_at,
      updateLabel: `${latest.release} deprivation data`,
    };
  },
  community_area_jsna: (latest) => {
    if (!latest.indicators || latest.indicators.length === 0) return null;
    return {
      figure: String(latest.indicators.length),
      unit: `indicators · ${latest.geography.label}`,
      hasSpark: false,
      fetchedAt: latest.fetched_at,
      updateLabel: `${latest.report_edition} data pack`,
    };
  },
  // Compact hemicycle from pipeline/elections_charts.py, same
  // has-a-mini-chart-or-fall-back-to-text pattern as imd_deprivation
  // above. Links to /data/local-elections/ for the full chart (with
  // legend) and this locality's own current divisions.
  local_elections: (latest, slug) => {
    if (latest.current_composition_largest_party === undefined) return null; // pipeline/elections_charts.py hasn't run
    const chartSvg = readChartSvg(DATA_ROOT, slug, "local_elections", "hemicycle_mini");
    return {
      figure: chartSvg ? null : latest.current_composition_largest_party_short,
      chartSvg,
      unit: `${latest.current_composition_largest_party_short} largest party, ${latest.current_composition[latest.current_composition_largest_party]}/${latest.current_composition_total_seats} seats`,
      hasSpark: false,
      fetchedAt: latest.fetched_at,
      updateLabel: `council composition as of ${latest.current_composition_as_of}`,
    };
  },
  parliamentary_elections: (latest) => {
    if (latest.elected_party === undefined) return null; // pipeline/elections_charts.py hasn't run
    return {
      figure: latest.elected_party_short,
      unit: `held since ${latest.latest_election_date}, ${latest.elected_party_vote_share_pct}% of the vote`,
      hasSpark: false,
      fetchedAt: latest.fetched_at,
      updateLabel: `${latest.latest_election_date} general election result`,
    };
  },
};

module.exports = function () {
  const config = loadConfig();
  if (!config) return [];
  const slug = config.locality.slug;

  return Object.entries(config.sources || {}).map(([key, sourceConfig]) => {
    const meta = CARD_META[key] || { title: key, desc: () => "" };
    const page = sourceConfig.slug ? `/data/${sourceConfig.slug}/` : null;
    const found = sourceConfig.enabled ? latestFile(DATA_ROOT, slug, key) : null;
    const formatter = found ? FIGURE_FORMATTERS[key] : null;
    const f = formatter ? formatter(found.data, slug) : null;

    if (f) {
      return {
        key,
        title: meta.title,
        page,
        isSoon: false,
        figure: f.figure,
        chartSvg: f.chartSvg || null,
        unit: f.unit,
        desc: meta.desc(config),
        hasSpark: !!f.hasSpark,
        sparkPoints: f.sparkPoints || "",
        fetchedAt: f.fetchedAt || null,
        updateLabel: f.updateLabel || null,
      };
    }

    return {
      key,
      title: meta.title,
      page,
      isSoon: true,
      figure: "—",
      chartSvg: null,
      unit: "coming soon",
      desc: meta.desc(config),
      hasSpark: false,
      sparkPoints: "",
      fetchedAt: null,
      updateLabel: null,
    };
  });
};
