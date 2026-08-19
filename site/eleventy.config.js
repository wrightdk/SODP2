module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/assets");
  eleventyConfig.addPassthroughCopy("src/styles.css");
  // Serves data/processed/ at /data/ so source pages can link a real
  // "download the JSON" file, not just describe the data.
  eleventyConfig.addPassthroughCopy({ "../data/processed": "data" });

  return {
    // Project Pages serves this site at /SODP2/, not the domain root.
    // Set via env so local `npm run serve`/`npm run build` stay at "/" —
    // only CI (deploy.yml) sets PATH_PREFIX. Every internal href/src in
    // the templates must go through the `url` filter to pick this up;
    // a hardcoded "/foo" bypasses it and 404s under the subpath.
    pathPrefix: process.env.PATH_PREFIX || "/",
    dir: {
      input: "src",
      output: "_site",
    },
  };
};
