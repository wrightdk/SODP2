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

const CARD_META = {
  ons_population: {
    title: "Population & Economy",
    page: "/population/",
    // LSOA-level (summed across the BUA's actual LSOA membership), not
    // local-authority-level — this used to report Wiltshire's population
    // (~500k) instead of Salisbury's. See CLAUDE.md.
    desc: (c) => `ONS small-area mid-year population estimate summed across ${c.locality.name}'s ${(c.geography.lsoa_codes || []).length} LSOAs.`,
  },
  police_crime: {
    title: "Police & Crime",
    page: "/crime/",
    desc: (c) => `Monthly incident counts from police.uk, filtered to a ${c.geography.radius_km}km radius of central ${c.locality.name}.`,
  },
  companies_house: {
    title: "Companies & Business",
    page: "/companies/",
    desc: (c) => `Active companies with a registered office in the ${(c.geography.postcode_prefixes || []).join("/")} postcode area, via Companies House.`,
  },
  council_transparency: {
    title: "Council Spending",
    page: null,
    desc: (c) => `Payments over £500 published by ${c.sources.council_transparency.council_name} under the transparency code.`,
  },
  planning_register: {
    title: "Planning Register",
    page: null,
    desc: (c) => `Planning applications from ${c.sources.council_transparency ? c.sources.council_transparency.council_name : "the council"}'s register.`,
  },
  imd_deprivation: {
    title: "Deprivation (IMD)",
    page: "/deprivation/",
    desc: (c) => `English Indices of Deprivation, joined per Lower-layer Super Output Area across ${c.locality.name}'s ${(c.geography.lsoa_codes || []).length} LSOAs.`,
  },
  local_elections: {
    title: "Local Elections",
    page: null,
    desc: () => "Ward-level results, once the local elections ingestion script is built.",
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
const FIGURE_FORMATTERS = {
  police_crime: (latest) => ({
    figure: String(latest.crime_count),
    unit: `incidents, ${latest.month}`,
    hasSpark: false,
    fetchedAt: latest.fetched_at,
    updateLabel: `${latest.month} incidents`,
  }),
  ons_population: (latest) => ({
    figure: latest.population.toLocaleString("en-GB"),
    unit: `residents, mid-${latest.year}`,
    hasSpark: false,
    fetchedAt: latest.fetched_at,
    updateLabel: `mid-${latest.year} population estimate`,
  }),
  companies_house: (latest) => ({
    figure: String(latest.active_count),
    unit: "active companies",
    hasSpark: false,
    fetchedAt: latest.fetched_at,
    updateLabel: `${latest.month} companies register`,
  }),
  // Replaces the plain "Decile N" text stat with the compact choropleth
  // from pipeline/imd_charts.py, per this session's scope — the card
  // links to /deprivation/ for the full map (with legend) and the
  // distribution chart. Falls back to the text figure if the chart
  // hasn't been generated yet (pipeline/ runs separately from ingest/).
  imd_deprivation: (latest, slug) => {
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
};

module.exports = function () {
  const config = loadConfig();
  if (!config) return [];
  const slug = config.locality.slug;

  return Object.entries(config.sources || {}).map(([key, sourceConfig]) => {
    const meta = CARD_META[key] || { title: key, page: null, desc: () => "" };
    const found = sourceConfig.enabled ? latestFile(DATA_ROOT, slug, key) : null;
    const formatter = found ? FIGURE_FORMATTERS[key] : null;

    if (found && formatter) {
      const f = formatter(found.data, slug);
      return {
        key,
        title: meta.title,
        page: meta.page,
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
      page: meta.page,
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
