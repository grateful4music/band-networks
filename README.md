# band-networks

A bipartite graph viz of connected music scenes. Bands and musicians are both nodes; an edge means "this musician was a member (or supporting musician) of this band." The viz can also project to band-only edges, or filter to "connectors" — musicians who appear in two or more bands.

The first scene is Seattle grunge (late 1980s through 1990s). The structure supports multiple scenes — drop a `scenes/<name>.toml` and run the build.

## Layout

```
scenes/<name>.toml          seed bands + metadata for a TOML-defined scene
data/<name>/network.json    crawl output (bipartite graph)
data/<name>/meta.json       scene metadata (kind, mbid, depth, built_at, stats)
data/<name>/popularity.json optional Last.fm listener counts
cache/                      shared MusicBrainz/Last.fm response cache
build_network.py            crawl a scene from MusicBrainz (CLI)
fetch_popularity.py         enrich a scene with Last.fm popularity
server.py                   FastAPI server: serves the viz + crawl API
index.html                  D3 force-directed viz with build modal
```

## Viz controls

- **Scene:** dropdown switches between built scenes. **+ Build new** opens a modal that searches MusicBrainz and builds a single-band network on demand. If the band has been built before, the modal shows an "already built" badge and switching is instant.
- **View:** Connectors / Full / Band-only.
- **Size by:** Centrality (network-derived) or Popularity (Last.fm listeners). Popularity is disabled until `popularity.json` exists for the active scene.
- **Click a node** to filter to its 2-hop neighborhood (1-hop in Band-only). Click again, or click empty space, to clear.

## Usage

```bash
# Run the server (serves viz at http://localhost:8765 and the build API)
uv run server.py

# Or use the CLI to build scenes directly:
uv run build_network.py --scene grunge
uv run build_network.py --band "Radiohead"          # depth 1 default
uv run build_network.py --band "Pearl Jam" --depth 2

# Optional: enrich with Last.fm popularity
export LASTFM_API_KEY=<your_key>                    # https://www.last.fm/api/account/create
uv run fetch_popularity.py --scene grunge
```

## API

- `GET  /api/scenes` — list built scenes with meta (id, name, kind, mbid, depth, stats).
- `GET  /api/search?q=<name>&limit=5` — MusicBrainz artist search.
- `POST /api/build` — body `{name, mbid, depth, force?}`. Returns `{status: "exists", ...}` if already built, otherwise `{status: "building", job_id}`.
- `GET  /api/build/{job_id}` — poll a build job. State is `queued`/`running`/`done`/`error`; `progress` updates per band crawled.

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
- Consider filtering crawl results by `area` and active period.
