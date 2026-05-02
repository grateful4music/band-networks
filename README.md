# band-networks

A bipartite graph of the Seattle grunge scene, late 1980s through the 1990s. Bands and musicians are both nodes; an edge means "this musician was a member (or supporting musician) of this band." The viz can also project to band-only edges, or filter to "connectors" — musicians who appear in two or more bands.

## Files

- `build_network.py` — fetches band/musician data from MusicBrainz starting from a curated seed list of canonical Seattle grunge bands. Caches API responses to `cache/` so re-runs don't re-hit the API. Emits `bands_network.json` in bipartite form.
- `bands_network.json` — bipartite graph data: `{ nodes: [...], edges: [...] }`.
- `bands_raw.json` — earlier depth-2 crawl from a Mother Love Bone seed (kept for reference; not used by the viz).
- `index.html` — D3 force-directed viz with three view modes:
  - **Full bipartite** — every band + musician.
  - **Band-only** — projection to band nodes; edge thickness = number of shared musicians.
  - **Connectors only** (default) — bipartite, but musicians in only one band are hidden.

## Usage

```bash
# View
open index.html  # or `python -m http.server` and visit localhost:8000

# Re-fetch (set a real contact email in build_network.py first)
uv run build_network.py
```

## TODOs

- Replace `your-email@example.com` in `build_network.py` with a real contact (MusicBrainz TOS).
- Verify the seed-list MBIDs and add any missing canonical bands.
- Consider filtering by `area` (Seattle) and active period (1988–1999) to prune crawl results.
