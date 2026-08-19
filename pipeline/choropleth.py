"""
choropleth.py — generic LSOA choropleth renderer, shared across every
source that wants to colour the locality's LSOAs by some value (IMD
first; population density, crime rate, and company density are meant to
reuse this unchanged in later sessions — see ANALYSIS_CHARTS_SPEC.md).

Nothing in here knows what "decile" or "IMD" mean. Callers supply the
value per LSOA, a colour scale, a value domain, and the caption text —
this module only projects geometry, maps values to colour, and lays out
an accessible SVG. Keep it that way: if you need to add IMD-specific (or
any other source-specific) logic, it belongs in the caller, not here.

Projection: a simple equirectangular projection (x = lon * cos(mean_lat),
y = lat), not a proper cartographic projection — deliberately. This is a
schematic map of ~28 adjacent small polygons covering a few square
kilometres, where the distortion a real projection corrects for is
imperceptible. A GIS library (geopandas/pyproj) would be real overkill
for this; see CLAUDE.md for that decision.

Renders one polygon per ring pair using the even-odd fill rule, which
handles simple polygons and polygons-with-holes identically without the
caller needing to know which it has.
"""

import math


def _project(lon, lat, cos_lat0):
    """Equirectangular: longitude compressed by cos(mean latitude), y
    kept as-is (flipped to SVG's y-down convention happens in fit_to_box)."""
    return lon * cos_lat0, lat


def _polygon_points(geometry, cos_lat0):
    """Yields one list of (x, y) per ring, projected but not yet scaled."""
    if geometry["type"] == "Polygon":
        rings = geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        rings = [ring for poly in geometry["coordinates"] for ring in poly]
    else:
        raise ValueError(f"Unsupported geometry type: {geometry['type']}")

    for ring in rings:
        yield [_project(lon, lat, cos_lat0) for lon, lat in ring]


def _fit_to_box(all_points, width, height, padding):
    xs = [x for pts in all_points for x, _ in pts]
    ys = [y for pts in all_points for _, y in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1
    usable_w = width - 2 * padding
    usable_h = height - 2 * padding
    scale = min(usable_w / span_x, usable_h / span_y)

    def to_svg(x, y):
        sx = padding + (x - min_x) * scale
        # flip y: latitude increases north, SVG y increases downward
        sy = padding + (max_y - y) * scale
        return sx, sy

    return to_svg


def interpolate_color(t, stops):
    """stops: sorted list of (position 0..1, (r,g,b)). Linear interpolation
    between the two nearest stops; clamps t to [0, 1]."""
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t0 <= t <= t1:
            local_t = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return tuple(round(c0[i] + (c1[i] - c0[i]) * local_t) for i in range(3))
    return stops[-1][1]


def _rgb_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def render_choropleth(
    features,
    values,
    *,
    color_scale,
    value_domain,
    title,
    desc,
    value_label_fn,
    legend_ticks,
    legend_caption="",
    width=640,
    height=480,
    padding=24,
    no_data_color=(230, 230, 230),
    show_legend=True,
):
    """
    features: GeoJSON features with LSOA21CD in properties and a geometry.
    values: {lsoa_code: float} — LSOAs missing from this dict render in
        no_data_color rather than being silently dropped from the map.
    color_scale: sorted [(t, (r,g,b)), ...] for interpolate_color, t in [0,1].
        Lower values map to earlier stops — reverse the list yourself if a
        low value should be the most intense colour.
    value_domain: (min, max) that values are normalised against to get t.
    value_label_fn: (lsoa_code, value_or_None) -> str, used as each
        polygon's <title> for screen readers.
    legend_ticks: [(t, label), ...] drawn under the legend gradient bar.
    show_legend: set False for a compact/card-sized map with no legend —
        the map fills the whole height instead of reserving space for it.
        Per-polygon <title> accessibility is unaffected either way; only
        use a legend-less render somewhere the full chart (with legend)
        is also reachable, e.g. a homepage card linking to a detail page.
    """
    lats = [lat for f in features for ring in _polygon_points(f["geometry"], 1.0) for _, lat in ring]
    mean_lat = sum(lats) / len(lats)
    cos_lat0 = math.cos(math.radians(mean_lat))

    map_height = height - 70 if show_legend else height  # reserve space for the legend, if shown
    projected = {
        f["properties"]["LSOA21CD"]: list(_polygon_points(f["geometry"], cos_lat0)) for f in features
    }
    all_points = [pts for rings in projected.values() for pts in rings]
    to_svg = _fit_to_box(all_points, width, map_height, padding)

    domain_min, domain_max = value_domain
    domain_span = (domain_max - domain_min) or 1

    path_elements = []
    for f in features:
        code = f["properties"]["LSOA21CD"]
        name = f["properties"].get("LSOA21NM", code)
        value = values.get(code)

        if value is None:
            fill = _rgb_hex(no_data_color)
        else:
            t = (value - domain_min) / domain_span
            fill = _rgb_hex(interpolate_color(t, color_scale))

        subpaths = []
        for ring in projected[code]:
            svg_pts = [to_svg(x, y) for x, y in ring]
            d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in svg_pts) + " Z"
            subpaths.append(d)

        label = value_label_fn(code, value)
        path_elements.append(
            f'<path d="{" ".join(subpaths)}" fill="{fill}" fill-rule="evenodd" '
            f'stroke="var(--bg-elevated, #fff)" stroke-width="1"><title>{_escape(name)}: {_escape(label)}</title></path>'
        )

    legend_svg = (
        _render_legend(color_scale, legend_ticks, legend_caption, width, padding, y=map_height + 12)
        if show_legend
        else ""
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="choropleth-title choropleth-desc">'
        f'<title id="choropleth-title">{_escape(title)}</title>'
        f'<desc id="choropleth-desc">{_escape(desc)}</desc>'
        f"{''.join(path_elements)}"
        f"{legend_svg}"
        f"</svg>"
    )


def _render_legend(color_scale, legend_ticks, caption, width, padding, y):
    bar_x = padding
    bar_w = width - 2 * padding
    bar_h = 14
    stop_els = "".join(
        f'<stop offset="{t * 100:.0f}%" stop-color="{_rgb_hex(rgb)}" />' for t, rgb in color_scale
    )
    gradient_id = "choropleth-legend-gradient"
    tick_els = []
    for t, label in legend_ticks:
        tx = bar_x + t * bar_w
        anchor = "start" if t <= 0.02 else "end" if t >= 0.98 else "middle"
        tick_els.append(
            f'<text x="{tx:.1f}" y="{y + bar_h + 16}" font-size="11" fill="var(--text-muted, #666)" '
            f'text-anchor="{anchor}">{_escape(label)}</text>'
        )
    caption_el = (
        f'<text x="{bar_x}" y="{y - 6}" font-size="11" fill="var(--text-muted, #666)">{_escape(caption)}</text>'
        if caption
        else ""
    )
    return (
        f"<defs><linearGradient id=\"{gradient_id}\" x1=\"0\" x2=\"1\" y1=\"0\" y2=\"0\">{stop_els}</linearGradient></defs>"
        f"{caption_el}"
        f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="url(#{gradient_id})" '
        f'stroke="var(--border, #ccc)" stroke-width="1" />'
        f"{''.join(tick_els)}"
    )


def _escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
