# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A bipartite graph visualization of connected music scenes. Bands and musicians are both nodes; an edge means "this musician was a member (or supporting musician) of this band." The viz can project to band-only edges and filter to "connectors" — musicians who appear in two or more bands.

Designed as an evolving exploration platform — multiple scenes (TOML-defined) plus on-demand single-band builds from the web UI. The first scene is Seattle grunge.

## Running

Python 3.12+, `uv` for dependency management. No test suite.

```bash
uv run server.py                              # FastAPI at http://localhost:8765 (auto-reload)
uv run build_network.py --scene grunge        # build a TOML-defined scene
uv run build_network.py --band "Radiohead"    # single-band scene, depth 1
uv run build_network.py --band "Pearl Jam" --depth 2
uv run fetch_popularity.py --scene grunge     # enrich with Last.fm listener counts
```

Last.fm requires `LASTFM_API_KEY` (loaded from `.env` by `server.py`, or `export`ed for CLI use).

## Architecture

Three Python entry points cooperate via the filesystem:

- **`build_network.py`** — MusicBrainz crawler. BFS from seed bands to a depth limit; emits `data/<scene>/network.json`. Per-MBID cache at `cache/<mbid>.json`; rate-limited at 1.1s/request (MusicBrainz TOS). The same module is imported by the server (`build_single_artist`, `search_artist`, `find_existing_by_mbid`) for on-demand builds.
- **`fetch_popularity.py`** — Last.fm enrichment. Writes `data/<scene>/popularity.json` keyed by MBID; cache at `cache/lastfm/<mbid>.json`. `fetch_popularity_for_scene()` is also called by the server as phase 2 of a build.
- **`server.py`** — FastAPI app. Serves `index.html`, the `/data/` tree (static), and the build API (`/api/search`, `/api/build`, `/api/build/{job_id}`, `/api/scenes`, `/api/config`). Build jobs run in daemon threads with an in-memory `JOBS` dict — lost on restart, capped at 50 with FIFO eviction of finished jobs. After MusicBrainz finishes, the job auto-chains into Last.fm if `LASTFM_API_KEY` is set; popularity failures only emit a `popularity_warning` rather than failing the build.

Scene metadata lives in `data/<scene>/meta.json`: `kind` is `"scene"` (TOML-defined) or `"single-artist"` (ad-hoc; covers both Group and Person seeds); `mbid` is set only for single-artist scenes and is the key for "already built" deduplication. `_scene_meta()` in `server.py` falls back to synthesizing meta from `network.json` + the source TOML for legacy scenes built before `meta.json` existed — keep this fallback working when changing the meta shape.

`index.html` is a single-file D3 force-directed viz with a build modal (uses `/api/search` for autocomplete, `/api/build` to start, polls `/api/build/{job_id}`).

## Bipartite invariants

The graph must stay bipartite: musician ↔ band, never musician ↔ musician or band ↔ band. Two places enforce this:

- **Person seeds are inverted.** When a seed's MusicBrainz `type` is `"person"`, `build()` adds them as a musician and uses their bands as the BFS seeds. Without this the BFS would treat the person as a band and their bands as members, inverting roles. See the seed loop in `build_network.py`.
- **Relationship filter is symmetric.** `_members_of` and `_bands_of` accept the same MusicBrainz relation types (`member of band`, `member`, `supporting musician`). Drift between them silently breaks the symmetry between "this band's members" and "this musician's bands."

## Data layout

```
scenes/<name>.toml              # seed list + max_depth for TOML-defined scenes
data/<scene>/network.json       # {nodes: [...], edges: [...]} — the bipartite graph
data/<scene>/meta.json          # {id, name, kind, mbid, depth, built_at, stats}
data/<scene>/popularity.json    # {mbid: {listeners, playcount}}
cache/<mbid>.json               # raw MusicBrainz artist+relationships
cache/lastfm/<mbid>.json        # raw Last.fm artist.getInfo
```

Single-artist scene `id` = `slugify(name)`; on slug collision with a different MBID, the slug gets an 8-char MBID suffix.

---

## Behavioral guidelines

These bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think before coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity first

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

### 3. Surgical changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that *your* changes made unused; don't remove pre-existing dead code unless asked.

Every changed line should trace directly to the user's request.

### 4. Goal-driven execution

Define verifiable success criteria before starting.

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"
