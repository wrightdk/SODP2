// Reads whatever ingest/ scripts have already written to /data/processed —
// this file never fetches or computes anything itself, per CLAUDE.md's
// "narrative/site never computes" rule. One locality per subdirectory of
// data/processed/, so this generalizes automatically as more localities
// and sources are added — nothing here is Salisbury-specific.
const fs = require("fs");
const path = require("path");

const PROCESSED_DIR = path.join(__dirname, "../../../data/processed");

function latestPoliceCrime(slug) {
  const crimeDir = path.join(PROCESSED_DIR, slug, "police_crime");
  if (!fs.existsSync(crimeDir)) return null;

  const months = fs
    .readdirSync(crimeDir)
    .filter((f) => f.endsWith(".json"))
    .sort();
  if (months.length === 0) return null;

  const latestFile = months[months.length - 1];
  return JSON.parse(fs.readFileSync(path.join(crimeDir, latestFile), "utf-8"));
}

module.exports = function () {
  if (!fs.existsSync(PROCESSED_DIR)) return [];

  return fs
    .readdirSync(PROCESSED_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({
      slug: entry.name,
      policeCrime: latestPoliceCrime(entry.name),
    }))
    .filter((locality) => locality.policeCrime !== null);
};
