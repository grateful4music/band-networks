"""Fetch Last.fm popularity (listeners + playcount) by MBID for every band in
bands_network.json. Writes popularity.json: {mbid: {listeners, playcount}}.

Setup:
    1. Get a free API key: https://www.last.fm/api/account/create
    2. export LASTFM_API_KEY=<your_key>
    3. uv run fetch_popularity.py
"""

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
INPUT_PATH = ROOT / "bands_network.json"
OUTPUT_PATH = ROOT / "popularity.json"
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
    if not API_KEY:
        raise SystemExit(
            "LASTFM_API_KEY env var not set. Get a key at "
            "https://www.last.fm/api/account/create then `export LASTFM_API_KEY=...`"
        )

    graph = json.loads(INPUT_PATH.read_text())
    bands = [n for n in graph["nodes"] if n["type"] == "band"]
    print(f"Fetching popularity for {len(bands)} bands...")

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

    OUTPUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUTPUT_PATH.name}: {len(out)} bands with popularity data.")


if __name__ == "__main__":
    main()
