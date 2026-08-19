"""
imd_charts.py — the two IMD charts described in ANALYSIS_CHARTS_SPEC.md:
a choropleth of decile across the locality's LSOAs, and a distribution
bar chart of how many LSOAs fall in each national decile (1-10).

This is /pipeline/, not /ingest/: it reads already-ingested data from
data/processed/ (written by ingest/imd_deprivation.py) and the boundary
geometry cached by fetch_lsoa_boundaries.py, makes no network calls, and
also computes this source's one locality-level stat — average_decile —
writing it back into the same processed file ingest/imd_deprivation.py
wrote. Run after ingest/imd_deprivation.py, not instead of it.

Colour scale: ColorBrewer's YlOrRd (Yellow-Orange-Red), a published
colourblind-safe sequential scheme — reversed here so decile 1 (most
deprived) gets the most intense colour, matching the common cartographic
convention for deprivation maps, and decile 10 (least deprived) gets the
palest. Captions stay factual ("LSOA X falls in decile N") rather than
framing any area as a finding — these are real neighbourhoods.

Usage:
    python pipeline/imd_charts.py --config config/salisbury.yml
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from choropleth import interpolate_color, render_choropleth
from common import latest_processed_path, merge_fields

import yaml

# ColorBrewer YlOrRd (9-class), reversed: index 0 = decile 1 (most deprived).
YLORRD_REVERSED = [
    (0 / 8, (128, 0, 38)),
    (1 / 8, (189, 0, 38)),
    (2 / 8, (227, 26, 28)),
    (3 / 8, (252, 78, 42)),
    (4 / 8, (253, 141, 60)),
    (5 / 8, (254, 178, 76)),
    (6 / 8, (254, 217, 118)),
    (7 / 8, (255, 237, 160)),
    (8 / 8, (255, 255, 204)),
]


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_distribution_bar(decile_counts, *, title, desc, width=640, height=280, padding=32):
    """decile_counts: {1: n, 2: n, ..., 10: n}. Horizontal bars, one per decile."""
    max_count = max(decile_counts.values()) or 1
    bar_area_w = width - padding - 60
    row_h = (height - padding * 2) / 10

    bars = []
    for decile in range(1, 11):
        count = decile_counts.get(decile, 0)
        y = padding + (decile - 1) * row_h
        bar_w = (count / max_count) * bar_area_w if max_count else 0
        color = "#{:02x}{:02x}{:02x}".format(*interpolate_color((decile - 1) / 9, YLORRD_REVERSED))
        bars.append(
            f'<text x="{padding + 20}" y="{y + row_h * 0.65:.1f}" font-size="12" text-anchor="end" '
            f'fill="var(--text-muted, #666)">{decile}</text>'
            f'<rect x="{padding + 28}" y="{y + row_h * 0.15:.1f}" width="{bar_w:.1f}" height="{row_h * 0.7:.1f}" fill="{color}" />'
            f'<text x="{padding + 28 + bar_w + 6:.1f}" y="{y + row_h * 0.65:.1f}" font-size="12" '
            f'fill="var(--text, #222)">{count}</text>'
            f"<title>Decile {decile}: {count} LSOA{'s' if count != 1 else ''}</title>"
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="dist-title dist-desc">'
        f'<title id="dist-title">{title}</title>'
        f'<desc id="dist-desc">{desc}</desc>'
        f'<text x="{padding}" y="16" font-size="11" fill="var(--text-muted, #666)">Decile (1 = most deprived)</text>'
        f"{''.join(bars)}"
        f"</svg>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    args = parser.parse_args()

    config = load_config(args.config)
    slug = config["locality"]["slug"]

    imd_path = latest_processed_path(slug, "imd_deprivation")
    imd = json.loads(imd_path.read_text(encoding="utf-8"))
    boundaries_path = Path("data/reference") / f"lsoa_boundaries_{slug}.geojson"
    if not boundaries_path.exists():
        raise FileNotFoundError(f"{boundaries_path} not found — run fetch_lsoa_boundaries.py first.")
    boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))

    values = {lsoa["lsoa_code"]: lsoa["imd_decile"] for lsoa in imd["lsoas"]}

    def label_fn(code, value):
        if value is None:
            return "no IMD data"
        return f"falls in IMD decile {value} of 10"

    locality_name = config["locality"]["name"]
    choropleth_svg = render_choropleth(
        boundaries["features"],
        values,
        color_scale=YLORRD_REVERSED,
        value_domain=(1, 10),
        title=f"Index of Multiple Deprivation by LSOA, {locality_name}",
        desc=(
            f"Choropleth map of {locality_name}'s {len(boundaries['features'])} LSOAs, "
            f"coloured by IMD decile ({imd['release']}). Decile 1 is the most deprived "
            f"10% of LSOAs in England, decile 10 the least."
        ),
        value_label_fn=label_fn,
        legend_ticks=[(0, "1 (most deprived)"), (0.5, "5-6"), (1, "10 (least deprived)")],
        legend_caption=f"IMD decile, {imd['release']}",
    )

    # Compact version for the homepage card: no legend (the card links to
    # this page, where the full chart with legend lives), small enough to
    # sit where the card's headline stat used to be.
    choropleth_mini_svg = render_choropleth(
        boundaries["features"],
        values,
        color_scale=YLORRD_REVERSED,
        value_domain=(1, 10),
        title=f"IMD decile by LSOA, {locality_name}",
        desc=f"Small choropleth of {locality_name}'s LSOAs by IMD decile — see the full map for a legend.",
        value_label_fn=label_fn,
        legend_ticks=[],
        width=240,
        height=140,
        padding=6,
        show_legend=False,
    )

    decile_counts = {d: 0 for d in range(1, 11)}
    for lsoa in imd["lsoas"]:
        decile_counts[lsoa["imd_decile"]] = decile_counts.get(lsoa["imd_decile"], 0) + 1

    distribution_svg = render_distribution_bar(
        decile_counts,
        title=f"IMD decile distribution across {locality_name}'s LSOAs",
        desc=(
            f"Bar chart showing how many of {locality_name}'s {len(imd['lsoas'])} LSOAs fall in "
            f"each IMD decile from 1 (most deprived) to 10 (least deprived), {imd['release']}."
        ),
    )

    out_dir = Path("data/processed") / slug / "imd_deprivation" / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "choropleth.svg").write_text(choropleth_svg, encoding="utf-8")
    (out_dir / "choropleth_mini.svg").write_text(choropleth_mini_svg, encoding="utf-8")
    (out_dir / "distribution.svg").write_text(distribution_svg, encoding="utf-8")
    print(f"Wrote choropleth.svg, choropleth_mini.svg, and distribution.svg to {out_dir}")

    # The locality-level summary stat, computed here (not in ingest/) per
    # CLAUDE.md rule 1 — and from the same decile_counts this file already
    # built for the distribution chart, rather than a second pass over
    # imd["lsoas"] that could drift out of sync with it.
    average_decile = round(sum(decile * count for decile, count in decile_counts.items()) / len(imd["lsoas"]))
    merge_fields(
        imd_path,
        average_decile=average_decile,
        average_decile_method="unweighted mean of IMD decile across matched LSOAs",
    )
    print(f"average_decile = {average_decile} for {slug} ({imd['release']}) in {imd_path}")


if __name__ == "__main__":
    main()
