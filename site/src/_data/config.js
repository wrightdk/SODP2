// Single-locality site for now: this build serves whichever config is
// found first under /config/. Revisit once the site needs to serve more
// than one locality at once (see CLAUDE.md's portability model) — this
// file never fetches or computes anything, it just exposes what's on
// disk, per CLAUDE.md's "narrative/site never computes" rule.
const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

const CONFIG_DIR = path.join(__dirname, "../../../config");

module.exports = function () {
  if (!fs.existsSync(CONFIG_DIR)) return null;

  const files = fs
    .readdirSync(CONFIG_DIR)
    .filter((f) => f.endsWith(".yml") || f.endsWith(".yaml"));
  if (files.length === 0) return null;

  const raw = fs.readFileSync(path.join(CONFIG_DIR, files[0]), "utf-8");
  return yaml.load(raw);
};
