"""
elections_charts.py — three charts described in the elections phase brief:
1. a line chart of party vote share across the locality's last 3 general
   elections (from ingest/parliamentary_elections.py's output),
2. the same chart type for the locality's last 3 *local* elections,
   summed across its own divisions (from ingest/local_elections.py's
   output),
3. a semicircle ("hemicycle") chart of the council's CURRENT party
   composition — the most recent result per individual seat, not just
   the last full election's results (see current_composition() below
   for why those two aren't always the same thing, and how this
   actually tells them apart rather than assuming).

No new charting dependency: same hand-rolled SVG approach as
choropleth.py/imd_charts.py (stdlib only — line charts and a semicircle
of dots are simple enough geometry not to need one).

Colour/left-right ordering: UK party colours below follow each party's
own public brand colour (as commonly reproduced in UK election
coverage, not any officially licensed palette) and the left-to-right
ordering follows the conventional placement used in UK hemicycle charts
(broadly left to right along the political spectrum) — see
PARTY_LEFT_RIGHT_ORDER. A party not in that list gets a deterministic
fallback colour and is placed just right of "Independent", not because
that's a real ideological claim, only so the chart never breaks on an
unexpected party name.

Usage:
    python pipeline/elections_charts.py --config config/salisbury.yml
"""

import argparse
import colorsys
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import latest_processed_path, merge_fields

import yaml

# (short label, hex colour) per Democracy Club's party_name. Short labels
# keep the chart legend readable; "Conservative and Unionist Party" etc.
# are Democracy Club's/the Electoral Commission's registered full names.
PARTY_STYLES = {
    "Conservative and Unionist Party": ("Conservative", "#0087DC"),
    "Labour Party": ("Labour", "#E4003B"),
    "Labour and Co-operative Party": ("Labour", "#E4003B"),
    "Liberal Democrats": ("Liberal Democrats", "#FAA61A"),
    "Green Party": ("Green", "#02A95B"),
    "Reform UK": ("Reform UK", "#12B6CF"),
    "UK Independence Party (UKIP)": ("UKIP", "#70147A"),
    "Independent": ("Independent", "#909090"),
}
# Left-to-right seating order for the hemicycle and legend ordering.
# Anything not listed here is inserted right after "Independent",
# alphabetically among other unlisted parties — see module docstring.
PARTY_LEFT_RIGHT_ORDER = [
    "Green Party",
    "Labour Party",
    "Labour and Co-operative Party",
    "Independent",
    "Liberal Democrats",
    "Reform UK",
    "UK Independence Party (UKIP)",
    "Conservative and Unionist Party",
]


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def party_style(party_name: str):
    if party_name in PARTY_STYLES:
        return PARTY_STYLES[party_name]
    # Deterministic fallback colour so an unexpected party (a genuinely
    # local one, e.g. a residents' association) still renders distinctly
    # and consistently across re-runs, rather than crashing or reusing
    # another party's colour.
    digest = hashlib.sha256(party_name.encode("utf-8")).digest()
    hue = digest[0] / 255
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.75)
    return party_name, "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def left_right_rank(party_name: str) -> tuple:
    if party_name in PARTY_LEFT_RIGHT_ORDER:
        return (0, PARTY_LEFT_RIGHT_ORDER.index(party_name))
    independent_idx = PARTY_LEFT_RIGHT_ORDER.index("Independent")
    return (1 if party_name > "Independent" else -1, independent_idx, party_name)


def _escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------
# Chart 1 & 2: vote-share line chart (shared renderer)
# ---------------------------------------------------------------------

MINOR_PARTY_THRESHOLD_PCT = 3.0  # a party below this share in every
# shown election is folded into "Other" so the chart stays legible —
# see vote_share_series() below.


def vote_share_series(elections_by_date: dict):
    """elections_by_date: {date_label: {party_name: votes}}. Returns
    (dates, series) where series is a list of
    {party_name, short_label, color, shares: [pct, ...]} ordered by
    left_right_rank, plus a trailing "Other" entry if anything got
    folded. shares are 0-100, aligned 1:1 with dates."""
    dates = list(elections_by_date.keys())
    all_parties = sorted({p for votes in elections_by_date.values() for p in votes})

    major_parties = [
        p
        for p in all_parties
        if any(
            (votes.get(p, 0) / sum(votes.values()) * 100 if sum(votes.values()) else 0) >= MINOR_PARTY_THRESHOLD_PCT
            for votes in elections_by_date.values()
        )
    ]
    minor_parties = [p for p in all_parties if p not in major_parties]

    series = []
    for party in sorted(major_parties, key=left_right_rank):
        short_label, color = party_style(party)
        shares = []
        for votes in elections_by_date.values():
            total = sum(votes.values())
            shares.append(round(votes.get(party, 0) / total * 100, 1) if total else 0.0)
        series.append({"party_name": party, "short_label": short_label, "color": color, "shares": shares})

    if minor_parties:
        shares = []
        for votes in elections_by_date.values():
            total = sum(votes.values())
            other_votes = sum(votes.get(p, 0) for p in minor_parties)
            shares.append(round(other_votes / total * 100, 1) if total else 0.0)
        series.append({"party_name": "Other", "short_label": "Other", "color": "#8a8a8a", "shares": shares})

    return dates, series


def render_vote_share_line_chart(dates, series, *, title, desc, width=640, height=340, padding=44):
    plot_w = width - padding * 2
    plot_top = 28
    plot_h = height - plot_top - 110  # reserve room for x labels + legend
    max_share = max((s for series_item in series for s in series_item["shares"]), default=0)
    y_max = max(20.0, math.ceil((max_share * 1.15) / 10) * 10)

    def x_for(i):
        return padding + (i / (len(dates) - 1) if len(dates) > 1 else 0.5) * plot_w

    def y_for(share):
        return plot_top + plot_h - (share / y_max) * plot_h

    grid_els = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = plot_top + plot_h - frac * plot_h
        grid_els.append(
            f'<line x1="{padding}" y1="{y:.1f}" x2="{padding + plot_w}" y2="{y:.1f}" '
            f'stroke="var(--border, #ddd)" stroke-width="1" />'
            f'<text x="{padding - 8}" y="{y + 3:.1f}" font-size="10" text-anchor="end" '
            f'fill="var(--text-muted, #666)">{round(y_max * frac):.0f}%</text>'
        )

    x_labels = "".join(
        f'<text x="{x_for(i):.1f}" y="{plot_top + plot_h + 18}" font-size="12" text-anchor="middle" '
        f'fill="var(--text, #222)">{_escape(d)}</text>'
        for i, d in enumerate(dates)
    )

    line_els = []
    for s in series:
        points = [(x_for(i), y_for(share)) for i, share in enumerate(s["shares"])]
        path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        dots = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{s["color"]}">'
            f'<title>{_escape(s["short_label"])}, {_escape(dates[i])}: {s["shares"][i]:.1f}%</title></circle>'
            for i, (x, y) in enumerate(points)
        )
        line_els.append(
            f'<path d="{path}" fill="none" stroke="{s["color"]}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-linejoin="round" />{dots}'
        )

    legend_y = plot_top + plot_h + 44
    legend_els = []
    lx = padding
    for s in series:
        label = f'{s["short_label"]} ({s["shares"][-1]:.1f}%)'
        legend_els.append(
            f'<rect x="{lx}" y="{legend_y}" width="10" height="10" rx="2" fill="{s["color"]}" />'
            f'<text x="{lx + 15}" y="{legend_y + 9}" font-size="11.5" fill="var(--text, #222)">{_escape(label)}</text>'
        )
        lx += 18 + len(label) * 6.3
        if lx > width - padding - 100:
            lx = padding
            legend_y += 20

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="vsc-title vsc-desc">'
        f'<title id="vsc-title">{_escape(title)}</title>'
        f'<desc id="vsc-desc">{_escape(desc)}</desc>'
        f"{''.join(grid_els)}{x_labels}{''.join(line_els)}{''.join(legend_els)}"
        f"</svg>"
    )


# ---------------------------------------------------------------------
# Chart 3: hemicycle
# ---------------------------------------------------------------------

DOT_RADIUS = 6
MIN_SEAT_SPACING = DOT_RADIUS * 2 + 4


def _hemicycle_layout(total_seats: int, inner_radius=90, row_gap=20, max_rows=14):
    """Rows of increasing radius, each row's seat capacity proportional
    to its radius (arc length, for a fixed 180 degree span, is
    proportional to radius) so dot spacing stays roughly consistent
    across rows. Grows the row count until every row's *actual* assigned
    seat count fits within its capacity at MIN_SEAT_SPACING, so dots
    never overlap regardless of how many total seats there are."""
    num_rows = 1
    while num_rows <= max_rows:
        radii = [inner_radius + i * row_gap for i in range(num_rows)]
        total_radius = sum(radii)
        raw = [total_seats * r / total_radius for r in radii]
        counts = [int(x) for x in raw]
        remainder = total_seats - sum(counts)
        by_frac = sorted(range(num_rows), key=lambda i: -(raw[i] - counts[i]))
        for i in range(remainder):
            counts[by_frac[i]] += 1

        capacities = [math.floor(math.pi * r / MIN_SEAT_SPACING) + 1 for r in radii]
        if all(c <= cap for c, cap in zip(counts, capacities)):
            return radii, counts
        num_rows += 1

    # Fallback: last attempt, even if a little tight — better than an
    # infinite loop for a pathologically large seat count.
    return radii, counts


def render_hemicycle(seat_party_names, *, title, desc, width=640, padding=20, show_legend=True):
    """seat_party_names: a flat list, one entry per seat, of the party
    holding it — order doesn't matter, this groups and re-orders.
    show_legend=False renders a compact, legend-less version (with each
    dot's <title> still carrying its party for accessibility) for a
    homepage card — same show_legend convention as choropleth.py."""
    counts_by_party = defaultdict(int)
    for p in seat_party_names:
        counts_by_party[p] += 1

    ordered_parties = sorted(counts_by_party, key=left_right_rank)
    total_seats = len(seat_party_names)

    inner_radius = min(90, (width - 2 * padding) / 2 - 100)
    inner_radius = max(inner_radius, 40)
    radii, row_counts = _hemicycle_layout(total_seats, inner_radius=inner_radius)
    outer_radius = radii[-1] if radii else inner_radius

    cx = width / 2
    cy = padding + outer_radius + DOT_RADIUS

    # Ordered seat list, most-left party's seats first, so consuming it
    # row by row (each row spanning the full 180 degrees) keeps each
    # party's seats visually grouped into a contiguous wedge.
    ordered_seats = []
    for party in ordered_parties:
        short_label, color = party_style(party)
        ordered_seats.extend([(party, short_label, color)] * counts_by_party[party])

    dot_els = []
    cursor = 0
    for radius, row_count in zip(radii, row_counts):
        row_seats = ordered_seats[cursor: cursor + row_count]
        cursor += row_count
        for j, (party, short_label, color) in enumerate(row_seats):
            angle = math.pi - ((j + 0.5) / row_count) * math.pi if row_count else math.pi / 2
            x = cx + radius * math.cos(angle)
            y = cy - radius * math.sin(angle)
            dot_els.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{DOT_RADIUS}" fill="{color}">'
                f"<title>{_escape(short_label)}</title></circle>"
            )

    legend_els = []
    if show_legend:
        legend_y = cy + DOT_RADIUS + 24
        lx = padding
        for party in ordered_parties:
            short_label, color = party_style(party)
            label = f"{short_label} ({counts_by_party[party]})"
            legend_els.append(
                f'<rect x="{lx}" y="{legend_y}" width="10" height="10" rx="2" fill="{color}" />'
                f'<text x="{lx + 15}" y="{legend_y + 9}" font-size="11.5" fill="var(--text, #222)">{_escape(label)}</text>'
            )
            lx += 18 + len(label) * 6.3
            if lx > width - padding - 100:
                lx = padding
                legend_y += 20
        height = int(legend_y + 30)
    else:
        height = int(cy + DOT_RADIUS + padding)

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="hemi-title hemi-desc">'
        f'<title id="hemi-title">{_escape(title)}</title>'
        f'<desc id="hemi-desc">{_escape(desc)}</desc>'
        f"{''.join(dot_els)}{''.join(legend_els)}"
        f"</svg>"
    )


# ---------------------------------------------------------------------
# Data shaping from the two ingest sources' processed output
# ---------------------------------------------------------------------


def parliamentary_vote_share(results: list, last_n=3):
    """results: flat candidate rows from parliamentary_elections's
    processed file (one constituency, general elections only)."""
    by_date = defaultdict(lambda: defaultdict(int))
    for r in results:
        by_date[r["election_date"]][r["party_name"]] += int(r["votes_cast"] or 0)
    last_dates = sorted(by_date)[-last_n:]
    return {d: dict(by_date[d]) for d in last_dates}


def local_division_names_for_year(results: list, election_date: str, bua_name: str):
    """Which of this election's divisions belong to the locality — see
    config/salisbury.yml's local_elections comment for why this is a
    name-prefix match against the whole council's data, not a lookup
    against a static config.geography.wards list: division boundaries
    (and names/codes) changed between election years, and wards is only
    ever the current set."""
    prefix = f"{bua_name} "
    return {r["post_label"] for r in results if r["election_date"] == election_date and r["post_label"].startswith(prefix)}


def local_vote_share(results: list, bua_name: str, last_n=3):
    """Ordinary (non-by-election) elections only — a by-election covers
    one seat, not a comparable 'this year's result across all of the
    locality's divisions' data point for the line chart."""
    ordinary = [r for r in results if r["by_election"].strip().lower() not in ("t", "true")]
    all_dates = sorted({r["election_date"] for r in ordinary})
    last_dates = all_dates[-last_n:]

    by_date = {}
    division_counts = {}
    for d in last_dates:
        local_divisions = local_division_names_for_year(ordinary, d, bua_name)
        division_counts[d] = len(local_divisions)
        votes = defaultdict(int)
        for r in ordinary:
            if r["election_date"] == d and r["post_label"] in local_divisions:
                votes[r["party_name"]] += int(r["votes_cast"] or 0)
        by_date[d] = dict(votes)
    return by_date, division_counts


def current_composition(results: list):
    """The most recent result per individual seat — NOT just the most
    recent full election's results, though today (no Wiltshire
    by-election has happened since the last full election, checked
    against this run's data) the two happen to be identical. The
    difference matters whenever a by-election *has* occurred since:

    1. Anchor on the most recent ORDINARY (non-by-election) election —
       the set of divisions it contested defines "the current 98 (or
       however many) seats" under the boundaries in force today. This
       step matters because older, boundary-review-superseded divisions
       (different GSS codes, sometimes different names) are still
       present in the full history and would otherwise be miscounted as
       still-live seats.
    2. For each of those current seats, look at every row for that
       exact GSS code (its anchor result, plus any by-election since)
       and take whichever has the latest election_date — that's who
       currently holds it.

    Returns (seats: [{post_label, gss, party_name, election_date}, ...],
    as_of: latest date used, anchor_date: the ordinary election that
    defined the current seat set). One dict per seat, not just a party
    name, so a caller can slice this to one locality's own seats (see
    main() below) as well as count it up whole-council for the
    hemicycle — one computation, two views, rather than two.
    """
    ordinary = [r for r in results if r["by_election"].strip().lower() not in ("t", "true")]
    if not ordinary:
        raise RuntimeError("No ordinary (non-by-election) results found — can't determine the current seat set.")
    anchor_date = max(r["election_date"] for r in ordinary)
    current_gss = {r["gss"] for r in ordinary if r["election_date"] == anchor_date}

    by_gss = defaultdict(list)
    for r in results:
        if r["gss"] in current_gss:
            by_gss[r["gss"]].append(r)

    seats = []
    for gss, rows in by_gss.items():
        latest = max(rows, key=lambda r: r["election_date"])
        winner = next((r for r in rows if r["election_date"] == latest["election_date"] and r["elected"].strip().lower() in ("t", "true")), None)
        if winner is None:
            continue  # e.g. a cancelled/void poll with no recorded winner yet
        seats.append(
            {
                "post_label": winner["post_label"],
                "gss": gss,
                "party_name": winner["party_name"],
                "election_date": latest["election_date"],
            }
        )

    as_of = max(s["election_date"] for s in seats)
    return seats, as_of, anchor_date


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to a locality config YAML file")
    args = parser.parse_args()

    config = load_config(args.config)
    slug = config["locality"]["slug"]
    locality_name = config["locality"]["name"]
    bua_name = config["geography"]["bua_name"]
    constituencies = config["geography"].get("parliamentary_constituencies", [])

    # --- Chart 1: general election vote share ---
    parl_path = latest_processed_path(slug, "parliamentary_elections")
    parl = json.loads(parl_path.read_text(encoding="utf-8"))
    parl_by_date = parliamentary_vote_share(parl["results"])
    dates, series = vote_share_series(parl_by_date)
    parl_svg = render_vote_share_line_chart(
        dates,
        series,
        title=f"General election vote share, {'/'.join(constituencies)} constituency",
        desc=(
            f"Line chart of party vote share in the {locality_name} constituency's last "
            f"{len(dates)} general elections ({', '.join(dates)})."
        ),
    )
    parl_out_dir = parl_path.parent / "charts"
    parl_out_dir.mkdir(parents=True, exist_ok=True)
    (parl_out_dir / "vote_share.svg").write_text(parl_svg, encoding="utf-8")
    print(f"Wrote {parl_out_dir / 'vote_share.svg'}")

    latest_date = dates[-1]
    latest_votes = parl_by_date[latest_date]
    winner_party = max(latest_votes, key=latest_votes.get) if latest_votes else None
    merge_fields(
        parl_path,
        latest_election_date=latest_date,
        elected_party=winner_party,
        # short_label duplicates party_style()'s first element — merged in
        # here so the site (JS/Nunjucks) never needs its own copy of the
        # party-name-shortening table to show a card/legend label.
        elected_party_short=party_style(winner_party)[0] if winner_party else None,
        elected_party_vote_share_pct=round(latest_votes[winner_party] / sum(latest_votes.values()) * 100, 1) if winner_party else None,
    )
    print(f"elected_party = {winner_party!r} for {slug} ({latest_date}) in {parl_path}")

    # --- Chart 2: local election vote share, summed across the locality's divisions ---
    local_path = latest_processed_path(slug, "local_elections")
    local = json.loads(local_path.read_text(encoding="utf-8"))
    local_by_date, division_counts = local_vote_share(local["results"], bua_name)
    for d, n in division_counts.items():
        if n == 0:
            print(f"WARNING: no divisions named '{bua_name} ...' found for the {d} election — check bua_name/data.")
    local_dates, local_series = vote_share_series(local_by_date)
    local_vote_svg = render_vote_share_line_chart(
        local_dates,
        local_series,
        title=f"Local election vote share, {locality_name}'s divisions",
        desc=(
            f"Line chart of party vote share summed across {locality_name}'s "
            f"{division_counts.get(local_dates[-1], '?')} council divisions in its last "
            f"{len(local_dates)} ordinary local elections ({', '.join(local_dates)})."
        ),
    )
    local_out_dir = local_path.parent / "charts"
    local_out_dir.mkdir(parents=True, exist_ok=True)
    (local_out_dir / "vote_share.svg").write_text(local_vote_svg, encoding="utf-8")
    print(f"Wrote {local_out_dir / 'vote_share.svg'}")

    # --- Chart 3: current council-wide composition (hemicycle) ---
    council_name = config["sources"]["local_elections"].get("council_name", "the council")
    seats, as_of, anchor_date = current_composition(local["results"])
    party_per_seat = [s["party_name"] for s in seats]
    composition_note = (
        f"as of {as_of}, same as the {anchor_date} election result"
        if as_of == anchor_date
        else f"as of {as_of} — updated by at least one by-election since the {anchor_date} full election"
    )
    hemicycle_svg = render_hemicycle(
        party_per_seat,
        title=f"{council_name} current composition",
        desc=f"Semicircle chart of {council_name}'s {len(party_per_seat)} seats by party, {composition_note}.",
    )
    (local_out_dir / "hemicycle.svg").write_text(hemicycle_svg, encoding="utf-8")
    print(f"Wrote {local_out_dir / 'hemicycle.svg'} ({composition_note})")

    # Compact, legend-less version for the homepage card — same
    # show_legend convention as imd_charts.py's choropleth_mini.
    hemicycle_mini_svg = render_hemicycle(
        party_per_seat,
        title=f"{council_name} composition",
        desc=f"Compact semicircle of {council_name}'s {len(party_per_seat)} seats by party — see the full page for a legend.",
        width=240,
        padding=6,
        show_legend=False,
    )
    (local_out_dir / "hemicycle_mini.svg").write_text(hemicycle_mini_svg, encoding="utf-8")
    print(f"Wrote {local_out_dir / 'hemicycle_mini.svg'}")

    seat_counts = dict(sorted(defaultdict(int, {p: party_per_seat.count(p) for p in set(party_per_seat)}).items()))
    largest_party = max(seat_counts, key=seat_counts.get)

    # This locality's own current divisions, sliced from the same
    # current_composition() computation the hemicycle counts — not a
    # second pass over local["results"] that could drift out of sync
    # with it. Small enough (one row per division) to show as a table on
    # the detail page, unlike the full council's ~100-seat results.
    salisbury_prefix = f"{bua_name} "
    salisbury_divisions = sorted(
        (
            {
                "post_label": s["post_label"],
                "party_name": s["party_name"],
                "party_short": party_style(s["party_name"])[0],
                "election_date": s["election_date"],
            }
            for s in seats
            if s["post_label"].startswith(salisbury_prefix)
        ),
        key=lambda s: s["post_label"],
    )
    if not salisbury_divisions:
        print(f"WARNING: no current divisions named '{bua_name} ...' found — check bua_name/data.")

    merge_fields(
        local_path,
        current_composition=seat_counts,
        current_composition_total_seats=len(seats),
        current_composition_largest_party=largest_party,
        current_composition_largest_party_short=party_style(largest_party)[0],
        current_composition_as_of=as_of,
        current_composition_anchor_election=anchor_date,
        locality_current_divisions=salisbury_divisions,
    )
    print(f"current_composition = {seat_counts} for {slug} in {local_path}")


if __name__ == "__main__":
    main()
