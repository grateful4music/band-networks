"""Fetch Last.fm popularity (listeners + playcount) by MBID for every band in
data/<scene>/network.json. Writes data/<scene>/popularity.json: {mbid: {listeners, playcount}}.

Setup:
    1. Get a free API key: https://www.last.fm/api/account/create
    2. export LASTFM_API_KEY=<your_key>
    3. uv run fetch_popularity.py [--scene <name>]

This module also exposes `fetch_popularity_for_scene()` for the FastAPI server
to call as the second phase of /api/build (after the MusicBrainz crawl).
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache" / "lastfm"

RATE_LIMIT_SECONDS = 0.25  # Last.fm allows 5 req/sec; 0.25s is conservative.


def fetch(mbid: str) -> dict | None:
    api_key = os.environ.get("LASTFM_API_KEY")
    if not api_key:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{mbid}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"  ! corrupt Last.fm cache for {mbid} ({e}); refetching")

    params = urllib.parse.urlencode({
        "method": "artist.getInfo",
        "mbid": mbid,
        "api_key": api_key,
        "format": "json",
    })
    url = f"https://ws.audioscrobbler.com/2.0/?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  ! {mbid}: {e}")
        return None
    cache_file.write_text(json.dumps(data, indent=2))
    time.sleep(RATE_LIMIT_SECONDS)
    return data


def fetch_popularity_for_scene(
    scene_id: str,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Fetch popularity for every band in data/<scene_id>/network.json, write
    data/<scene_id>/popularity.json, and return the resulting dict. Requires
    LASTFM_API_KEY (read at call time)."""
    if not os.environ.get("LASTFM_API_KEY"):
        raise RuntimeError("LASTFM_API_KEY env var not set")

    input_path = DATA_DIR / scene_id / "network.json"
    output_path = DATA_DIR / scene_id / "popularity.json"
    if not input_path.exists():
        raise FileNotFoundError(f"No network for scene '{scene_id}': {input_path}")

    graph = json.loads(input_path.read_text())
    bands = [n for n in graph["nodes"] if n["type"] == "band"]
    total = len(bands)

    out: dict[str, dict] = {}
    for i, band in enumerate(bands, 1):
        mbid = band["id"]
        result = fetch(mbid)
        if result and "artist" in result:
            stats = result["artist"].get("stats", {})
            try:
                listeners = int(stats.get("listeners", 0))
                playcount = int(stats.get("playcount", 0))
            except (TypeError, ValueError):
                listeners = playcount = 0
            out[mbid] = {"listeners": listeners, "playcount": playcount}
        if progress is not None:
            progress({"current": band["name"], "done": i, "total": total})

    output_path.write_text(json.dumps(out, indent=2))
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch Last.fm popularity for a scene's bands.")
    parser.add_argument("--scene", default="grunge", help="Scene name (data/<name>/network.json).")
    args = parser.parse_args()

    if not os.environ.get("LASTFM_API_KEY"):
        raise SystemExit(
            "LASTFM_API_KEY env var not set. Get a key at "
            "https://www.last.fm/api/account/create then `export LASTFM_API_KEY=...`"
        )

    def cli_progress(info: dict) -> None:
        print(f"  [{info['done']}/{info['total']}] {info['current']}")

    try:
        out = fetch_popularity_for_scene(args.scene, progress=cli_progress)
    except FileNotFoundError as e:
        raise SystemExit(str(e))

    output_path = DATA_DIR / args.scene / "popularity.json"
    print(f"\nWrote {output_path}: {len(out)} bands with popularity data.")


if __name__ == "__main__":
    main()
