# band-networks

A bipartite graph of the Seattle grunge scene, late 1980s through the 1990s. Bands and musicians are both nodes; an edge means "this musician was a member (or supporting musician) of this band." The viz can also project to band-only edges, or filter to "connectors" — musicians who appear in two or more bands.

## Files

- `build_network.py` — fetches band/musician data from MusicBrainz starting from a curated seed list of canonical Seattle grunge bands. Caches API responses to `cache/` so re-runs don't re-hit the API. Emits `bands_network.json` in bipartite form.
- `fetch_popularity.py` — fetches Last.fm listener counts per band (by MBID) and writes `popularity.json`. Optional; the viz works without it.
- `bands_network.json` — bipartite graph data: `{ nodes: [...], edges: [...] }`.
- `popularity.json` — `{ <mbid>: { listeners, playcount } }`. Optional.
- `bands_raw.json` — earlier depth-2 crawl from a Mother Love Bone seed (kept for reference; not used by the viz).
- `index.html` — D3 force-directed viz.

## Viz controls

- **View:** Connectors / Full / Band-only.
- **Size by:** Centrality (network-derived: how many other bands a band shares members with) or Popularity (Last.fm listener count). Popularity is disabled until `popularity.json` exists.
- **Click a node** to filter to its 2-hop neighborhood (1-hop in Band-only). Click again, or click empty space, to clear.

## Usage

```bash
# View
.venv/bin/python3 -m http.server 8765   # then open http://localhost:8765

# Re-fetch the network (set a real contact email in build_network.py first)
uv run build_network.py

# Optional: fetch Last.fm popularity to enable the Popularity sizing toggle
export LASTFM_API_KEY=<your_key>        # get one at https://www.last.fm/api/account/create
uv run fetch_popularity.py
```

## TODOs

- Replace `your-email@example.com` in `build_network.py` with a real contact (MusicBrainz TOS).
- Verify all seed-list MBIDs are correct (19 canonical bands now in CANONICAL_SEEDS).
- Consider filtering by `area` (Seattle) and active period (1988–1999) to prune crawl results.
