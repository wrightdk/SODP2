// Shared by every _data/*.js file that reads a single ingest source from
// data/processed/ — deliberately outside _data/ itself, since Eleventy
// would otherwise try to load this file as its own global data value.
const fs = require("fs");
const path = require("path");

function latestFile(processedDir, slug, sourceKey) {
  const dir = path.join(processedDir, slug, sourceKey);
  if (!fs.existsSync(dir)) return null;

  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".json")).sort();
  if (files.length === 0) return null;

  const latest = files[files.length - 1];
  return {
    data: JSON.parse(fs.readFileSync(path.join(dir, latest), "utf-8")),
    downloadPath: `/data/${slug}/${sourceKey}/${latest}`,
  };
}

// One entry per locality (subdirectory of data/processed/) that actually
// has this source's data — localities without it are omitted, not shown
// empty, per the same gating principle as the homepage cards.
function localitiesWithSource(processedDir, sourceKey, dataFieldName) {
  if (!fs.existsSync(processedDir)) return [];

  return fs
    .readdirSync(processedDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const found = latestFile(processedDir, entry.name, sourceKey);
      return found ? { slug: entry.name, [dataFieldName]: found.data, downloadPath: found.downloadPath } : null;
    })
    .filter(Boolean);
}

// Reads a chart SVG written by /pipeline/ alongside a source's processed
// JSON (data/processed/<slug>/<source>/charts/<name>.svg). Returns null
// if it doesn't exist yet — pipeline charts are generated separately
// from ingestion, so a page/card can predate its chart.
function readChartSvg(processedDir, slug, sourceKey, name) {
  const p = path.join(processedDir, slug, sourceKey, "charts", `${name}.svg`);
  return fs.existsSync(p) ? fs.readFileSync(p, "utf-8") : null;
}

module.exports = { latestFile, localitiesWithSource, readChartSvg };
