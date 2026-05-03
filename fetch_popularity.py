"""Fetch Last.fm popularity (listeners + playcount) by MBID for every band in
data/<scene>/network.json. Writes data/<scene>/popularity.json: {mbid: {listeners, playcount}}.

Setup:
    1. Get a free API key: https://www.last.fm/api/account/create
    2. export LASTFM_API_KEY=<your_key>
    3. uv run fetch_popularity.py [--scene <name>]
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache" / "lastfm"

API_KEY = os.environ.get("LASTFM_API_KEY")
RATE_LIMIT_SECONDS = 0.25  # Last.fm allows 5 req/sec; 0.25s is conservative.


def fetch(mbid: str) -> dict | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{mbid}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    params = urllib.parse.urlencode({
        "method": "artist.getInfo",
        "mbid": mbid,
        "api_key": API_KEY,
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


def main():
    parser = argparse.ArgumentParser(description="Fetch Last.fm popularity for a scene's bands.")
    parser.add_argument("--scene", default="grunge", help="Scene name (data/<name>/network.json).")
    args = parser.parse_args()

    if not API_KEY:
        raise SystemExit(
            "LASTFM_API_KEY env var not set. Get a key at "
            "https://www.last.fm/api/account/create then `export LASTFM_API_KEY=...`"
        )

    input_path = DATA_DIR / args.scene / "network.json"
    output_path = DATA_DIR / args.scene / "popularity.json"
    if not input_path.exists():
        raise SystemExit(f"No network for scene '{args.scene}': {input_path} not found.")

    graph = json.loads(input_path.read_text())
    bands = [n for n in graph["nodes"] if n["type"] == "band"]
    print(f"Fetching popularity for {len(bands)} bands in scene '{args.scene}'...")

    out: dict[str, dict] = {}
    for i, band in enumerate(bands, 1):
        mbid = band["id"]
        result = fetch(mbid)
        if not result or "artist" not in result:
            print(f"  [{i}/{len(bands)}] {band['name']}: no data")
            continue
        stats = result["artist"].get("stats", {})
        try:
            listeners = int(stats.get("listeners", 0))
            playcount = int(stats.get("playcount", 0))
        except (TypeError, ValueError):
            listeners = playcount = 0
        out[mbid] = {"listeners": listeners, "playcount": playcount}
        print(f"  [{i}/{len(bands)}] {band['name']}: {listeners:,} listeners")

    output_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {output_path}: {len(out)} bands with popularity data.")


if __name__ == "__main__":
    main()
