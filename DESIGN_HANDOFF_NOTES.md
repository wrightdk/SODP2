# Design handoff notes — homepage

Accompanies the exported Design-to-Code output for the "Open Salisbury"
homepage mockup. Four things need to change before this is built as the
real homepage — not aesthetic notes, structural ones.

## 1. Gate every card on whether its source is actually live

The mockup shows live-looking numbers (population, company count, council
spend, IMD decile) for sources that mostly aren't built yet — only police
ingestion exists and has real data in `data/processed/` right now.

Rule: a card only renders real numbers if its corresponding entry in
`config/*.yml`'s `sources:` block is `enabled: true` **and** a
corresponding file exists in `data/processed/`. Otherwise it renders the
same "SOON" state the mockup already uses for Local Elections and Planning
Register — extend that pattern to every not-yet-live card, don't leave it
as special-casing for just those two.

This matters more than it might seem: the whole site's pitch is "every
figure is traceable and nothing is unsourced." A card showing a plausible
but non-real number on day one would directly contradict that.

## 2. Compute the dataset count, don't hardcode it

The mockup's copy says "Nine national datasets" — write this as a
template value derived from counting `sources:` entries in config at
build time, not as typed prose. Same principle as not hardcoding
"Salisbury" anywhere — a count that's wrong for a second locality is the
same class of bug as a name that's wrong for a second locality.

## 3. Add hero image fields to the config schema

The hero photograph is locality-specific and currently has nowhere to
live in `config/*.yml`. Add:

```yaml
site:
  hero_image: "assets/hero-salisbury.jpg"
  hero_image_credit: "Photo: [source/photographer], [licence]"
```

Every locality needs its own photo and its own credit — don't assume the
exported design's specific image is reusable as a template default.

## 4. Sparklines need real historical data — confirm this exists first

The mockup's sparklines imply a time series per metric. Check whether the
pipeline is actually persisting historical snapshots (e.g. dated files in
`data/processed/`, or relying on git history) before wiring sparklines to
real data. If that doesn't exist yet, ship cards without a sparkline (or
with a static/flat placeholder marked as such) rather than fabricating a
trend line — same honesty principle as point 1.

## Also worth knowing

The exported output is likely React/HTML/CSS components from Claude
Design — this needs adapting into the existing 11ty templates in `/site/`,
not replacing 11ty with a different framework. See README's repo
structure and CLAUDE.md's rules before restructuring anything.
