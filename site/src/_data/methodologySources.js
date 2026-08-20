// Methodology page's data-sources table — built the same way as the Data
// hub (dataHub.js): loop over config.sources at build time rather than
// hand-typing rows, so this table can't drift from config the way the
// original drafted copy already had (its "coming soon" for local_elections
// was stale by the time this page was built).
//
// "Coverage" and "Filtered by" prose isn't itself in config (config only
// carries the filtering *mechanism* — geography_key / filter_method — not
// a human sentence describing it), so this file maps mechanism -> prose,
// the same "one piece of copy not sourced from config" pattern dataHub.js's
// TITLES and homeCards.js's CARD_META already use.
const path = require("path");
const loadConfig = require("./config.js");
const { latestFile } = require("../_helpers/sourceData.js");

const DATA_ROOT = path.join(__dirname, "../../../data/processed");

const TITLES = {
  ons_population: "ONS population & economic stats",
  police_crime: "Police.uk crime data",
  companies_house: "Companies House",
  council_transparency: "Council transparency (spend, planning)",
  planning_register: "Planning register",
  imd_deprivation: "Index of Multiple Deprivation",
  local_elections: "Local elections",
  parliamentary_elections: "General elections",
  community_area_jsna: "Community Area JSNA",
};

// Geographic coverage of the underlying dataset itself (not the slice this
// site takes of it) — same kind of source-level fact as a licence, so it
// belongs in this map rather than in config's per-locality filtering block.
const COVERAGE = {
  ons_population: "UK-wide",
  police_crime: "England, Wales, NI",
  companies_house: "UK-wide",
  council_transparency: "Varies by council",
  planning_register: "Varies by council",
  imd_deprivation: "England only",
  local_elections: "Ward-level, England/Wales",
  parliamentary_elections: "Constituency-level, England/Wales",
  community_area_jsna: "Community Area boundary, Wiltshire only",
};

// Human-readable label for how this source is filtered to the locality —
// derived from config's own geography_key/filter_method fields where a
// source uses that mechanism, falling back to a source-specific note for
// the sources that filter some other way (council_transparency,
// community_area_jsna, local_elections — see CLAUDE.md's "portable in
// pattern, not in specifics" section for why those three don't reduce to
// a single geography.* list).
const GEOGRAPHY_KEY_LABELS = {
  lsoa_codes: "LSOA codes",
  postcode_prefixes: "Postcode prefixes",
  parliamentary_constituencies: "Parliamentary constituency",
  local_authority_codes: "Local authority codes",
};

const FILTER_METHOD_LABELS = {
  radius: "Centroid + radius",
  force_name: "Police force name",
};

const FILTER_FALLBACKS = {
  council_transparency: "Council-specific format",
  planning_register: "Council-specific format",
  local_elections:
    "Whole council fetched; this locality's divisions selected downstream by name match — see coverage note",
  community_area_jsna: "Community Area name — a wider boundary than this site's other sources, see note",
};

function filteredByLabel(key, sourceConfig) {
  if (sourceConfig.geography_key) {
    return GEOGRAPHY_KEY_LABELS[sourceConfig.geography_key] || sourceConfig.geography_key;
  }
  if (sourceConfig.filter_method) {
    return FILTER_METHOD_LABELS[sourceConfig.filter_method] || sourceConfig.filter_method;
  }
  return FILTER_FALLBACKS[key] || "—";
}

module.exports = function () {
  const config = loadConfig();
  if (!config) return [];
  const slug = config.locality.slug;

  return Object.entries(config.sources || {}).map(([key, sourceConfig]) => {
    const found = sourceConfig.enabled ? latestFile(DATA_ROOT, slug, key) : null;

    return {
      key,
      title: TITLES[key] || key,
      coverage: COVERAGE[key] || "—",
      filteredBy: filteredByLabel(key, sourceConfig),
      isLive: !!found,
      isCommunityAreaJsna: key === "community_area_jsna",
    };
  });
};
