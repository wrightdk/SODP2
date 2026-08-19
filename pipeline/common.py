"""
common.py — shared helpers for pipeline stats scripts.

Every source follows the same shape: read the facts ingest/ already wrote
to data/processed/<slug>/<source>/<period>.json, compute derived numbers
from them, and write those numbers back into the same file. One file
stays the single thing the site reads; only *who* computes what changes.

This is deliberately small. If a second pipeline concern needs sharing
beyond "read latest, merge fields back in," extend it then — don't
pre-build for needs that don't exist yet.
"""

import json
from pathlib import Path


def latest_processed_path(slug: str, source_key: str) -> Path:
    d = Path("data/processed") / slug / source_key
    files = sorted(p for p in d.glob("*.json") if p.parent == d)
    if not files:
        raise FileNotFoundError(f"No processed data in {d} — run ingest/{source_key}.py first.")
    return files[-1]


def merge_fields(path: Path, **fields) -> dict:
    """Read the JSON at path, add/overwrite the given fields, write it back.
    Returns the full merged dict, in case the caller needs it."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
