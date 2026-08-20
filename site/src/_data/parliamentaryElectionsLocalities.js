// Reads whatever ingest/parliamentary_elections.py and
// pipeline/elections_charts.py have already written to /data/processed —
// this file never fetches or computes anything itself, per CLAUDE.md's
// "narrative/site never computes" rule.
const path = require("path");
const { localitiesWithSource, readChartSvg } = require("../_helpers/sourceData.js");

const PROCESSED_DIR = path.join(__dirname, "../../../data/processed");

module.exports = function () {
  return localitiesWithSource(PROCESSED_DIR, "parliamentary_elections", "parliamentaryElections").map((locality) => ({
    ...locality,
    voteShareSvg: readChartSvg(PROCESSED_DIR, locality.slug, "parliamentary_elections", "vote_share"),
  }));
};
