// Data hub (/data/) row list — built by looping over config.sources at
// build time, cross-checked against what's actually in data/processed/.
// Never a hand-typed list of links: add a source to config, run its
// ingest/ and pipeline/ scripts, and it appears here with zero template
// edits. Same enabled-in-config AND has-a-processed-file gating as the
// homepage cards (homeCards.js) — a source only shows as live if both
// are true, otherwise it shows the SOON state.
const path = require("path");
const loadConfig = require("./config.js");
const { latestFile } = require("../_helpers/sourceData.js");

const DATA_ROOT = path.join(__dirname, "../../../data/processed");

// Display title per source key — the one piece of copy not sourced from
// config (config only carries `description`, `slug`, and the filtering/
// update-cadence fields ingest/pipeline actually need). Same titles as
// homeCards.js's CARD_META.
const TITLES = {
  ons_population: "Population & Economy",
  police_crime: "Police & Crime",
  companies_house: "Companies & Business",
  council_transparency: "Council Spending",
  planning_register: "Planning Register",
  imd_deprivation: "Deprivation (IMD)",
  local_elections: "Local Elections",
  community_area_jsna: "Community Area JSNA",
};

module.exports = function () {
  const config = loadConfig();
  if (!config) return [];
  const slug = config.locality.slug;

  return Object.entries(config.sources || {}).map(([key, sourceConfig]) => {
    const found = sourceConfig.enabled ? latestFile(DATA_ROOT, slug, key) : null;

    return {
      key,
      title: TITLES[key] || key,
      description: sourceConfig.description || "",
      licence: "Open Government Licence v3",
      page: sourceConfig.slug ? `/data/${sourceConfig.slug}/` : null,
      isLive: !!found,
      fetchedAt: found ? found.data.fetched_at : null,
      downloadPath: found ? found.downloadPath : null,
    };
  });
};
