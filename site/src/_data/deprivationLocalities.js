// Reads whatever ingest/imd_deprivation.py and pipeline/imd_charts.py
// have already written to /data/processed — this file never fetches or
// computes anything itself, per CLAUDE.md's "narrative/site never
// computes" rule.
const path = require("path");
const { localitiesWithSource, readChartSvg } = require("../_helpers/sourceData.js");

const PROCESSED_DIR = path.join(__dirname, "../../../data/processed");

module.exports = function () {
  return localitiesWithSource(PROCESSED_DIR, "imd_deprivation", "deprivation").map((locality) => ({
    ...locality,
    choroplethSvg: readChartSvg(PROCESSED_DIR, locality.slug, "imd_deprivation", "choropleth"),
    distributionSvg: readChartSvg(PROCESSED_DIR, locality.slug, "imd_deprivation", "distribution"),
  }));
};
