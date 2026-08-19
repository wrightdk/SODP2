// Reads whatever ingest/imd_deprivation.py has already written to
// /data/processed — this file never fetches or computes anything
// itself, per CLAUDE.md's "narrative/site never computes" rule.
const path = require("path");
const { localitiesWithSource } = require("../_helpers/sourceData.js");

const PROCESSED_DIR = path.join(__dirname, "../../../data/processed");

module.exports = function () {
  return localitiesWithSource(PROCESSED_DIR, "imd_deprivation", "deprivation");
};
