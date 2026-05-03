# band-networks

A bipartite graph viz of connected music scenes. Bands and musicians are both nodes; an edge means "this musician was a member (or supporting musician) of this band." The viz can also project to band-only edges, or filter to "connectors" — musicians who appear in two or more bands.

The first scene is Seattle grunge (late 1980s through 1990s). The structure supports multiple scenes — drop a `scenes/<name>.toml` and run the build.

## Layout

```
scenes/<name>.toml          seed bands + metadata for a scene
data/<name>/network.json    crawl output (bipartite graph)
data/<name>/popularity.json optional Last.fm listener counts
cache/                      shared MusicBrainz/Last.fm response cache
build_network.py            crawl a scene from MusicBrainz
fetch_popularity.py         enrich a scene with Last.fm popularity
index.html                  D3 force-directed viz
```

## Viz controls

- **View:** Connectors / Full / Band-only.
- **Size by:** Centrality (network-derived: how many other bands a band shares members with) or Popularity (Last.fm listener count). Popularity is disabled until `popularity.json` exists.
- **Click a node** to filter to its 2-hop neighborhood (1-hop in Band-only). Click again, or click empty space, to clear.

## Usage

```bash
# View
.venv/bin/python3 -m http.server 8765   # then open http://localhost:8765

# Build a scene from its TOML
uv run build_network.py --scene grunge

# Build a single-band scene by artist name (depth 2 by default)
uv run build_network.py --band "Radiohead"
uv run build_network.py --band "Pearl Jam" --depth 1

# Optional: fetch Last.fm popularity to enable the Popularity sizing toggle
export LASTFM_API_KEY=<your_key>        # get one at https://www.last.fm/api/account/create
uv run fetch_popularity.py --scene grunge
```

## Adding a scene

Create `scenes/<name>.toml`:

```toml
name = "My Scene"
description = "..."
max_depth = 1

seeds = [
  { name = "Band Name", mbid = "<musicbrainz-id>" },
  ...
]
```

Then `uv run build_network.py --scene <name>`.

## TODOs

- Replace contact email in `build_network.py` with a real one (MusicBrainz TOS).
- FastAPI backend + scene dropdown in viz (in progress).
- Browser-driven single-band crawl with progress (in progress).
- Consider filtering crawl results by `area` and active period.
