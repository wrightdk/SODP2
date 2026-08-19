// Drives the homepage's "Updated N days ago" status bar from whichever
// live card was actually fetched most recently — real provenance, not
// invented copy. Returns null if nothing is live yet.
const loadHomeCards = require("./homeCards.js");

module.exports = function () {
  const cards = loadHomeCards().filter((c) => !c.isSoon && c.fetchedAt);
  if (cards.length === 0) return null;

  cards.sort((a, b) => new Date(b.fetchedAt) - new Date(a.fetchedAt));
  const latest = cards[0];
  const daysAgo = Math.floor((Date.now() - new Date(latest.fetchedAt).getTime()) / 86400000);

  return {
    daysAgo,
    title: latest.title,
    updateLabel: latest.updateLabel,
  };
};
