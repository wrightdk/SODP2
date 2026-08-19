// Homepage data-source cards, gated per DESIGN_HANDOFF_NOTES.md point 1:
// a card only shows real numbers if its source is `enabled: true` in
// config AND a processed file actually exists for it — otherwise it
// renders the SOON state. Card titles/descriptions are generic per
// source (not locality-specific), so this works unmodified for any
// locality config.
const fs = require("fs");
const path = require("path");
const loadConfig = require("./config.js");

const DATA_ROOT = path.join(__dirname, "../../../data/processed");

const CARD_META = {
  ons_population: {
    title: "Population & Economy",
    desc: (c) => `ONS mid-year population and economic indicators for the ${c.locality.name} built-up area.`,
  },
  police_crime: {
    title: "Police & Crime",
    desc: (c) => `Monthly incident counts from police.uk, filtered to a ${c.geography.radius_km}km radius of central ${c.locality.name}.`,
  },
  companies_house: {
    title: "Companies & Business",
    desc: (c) => `Company formations and dissolutions across the ${(c.geography.postcode_prefixes || []).join("/")} postcode area, via Companies House.`,
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
    desc: () => "English Indices of Deprivation, joined per Lower-layer Super Output Area.",
  },
  local_elections: {
    title: "Local Elections",
    desc: () => "Ward-level results, once the local elections ingestion script is built.",
  },
};

// Sources with a formatter here can render real numbers once they have
// enabled:true + processed data; sources without one always show SOON,
// even if data later appears, until someone teaches this file how to
// read that source's output shape.
const FIGURE_FORMATTERS = {
  police_crime: (latest) => ({
    figure: String(latest.crime_count),
    unit: `incidents, ${latest.month}`,
    // Only one month of processed data exists right now — no time series
    // to plot a sparkline from. See DESIGN_HANDOFF_NOTES.md point 4.
    hasSpark: false,
    fetchedAt: latest.fetched_at,
    updateLabel: `${latest.month} incidents`,
  }),
};

function latestProcessedFile(slug, sourceKey) {
  const dir = path.join(DATA_ROOT, slug, sourceKey);
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".json")).sort();
  if (files.length === 0) return null;
  return JSON.parse(fs.readFileSync(path.join(dir, files[files.length - 1]), "utf-8"));
}

module.exports = function () {
  const config = loadConfig();
  if (!config) return [];
  const slug = config.locality.slug;

  return Object.entries(config.sources || {}).map(([key, sourceConfig]) => {
    const meta = CARD_META[key] || { title: key, desc: () => "" };
    const latest = sourceConfig.enabled ? latestProcessedFile(slug, key) : null;
    const formatter = latest ? FIGURE_FORMATTERS[key] : null;

    if (latest && formatter) {
      const f = formatter(latest);
      return {
        key,
        title: meta.title,
        isSoon: false,
        figure: f.figure,
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
      isSoon: true,
      figure: "—",
      unit: "coming soon",
      desc: meta.desc(config),
      hasSpark: false,
      sparkPoints: "",
      fetchedAt: null,
      updateLabel: null,
    };
  });
};
