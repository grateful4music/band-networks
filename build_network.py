"""Crawl band/musician data from MusicBrainz and emit a bipartite graph.

Output schema (data/<scene>/network.json):
  {
    "nodes": [
      {"id": <mbid>, "name": <str>, "type": "band"},
      {"id": <mbid>, "name": <str>, "type": "musician", "band_count": <int>}
    ],
    "edges": [
      {"source": <musician mbid>, "target": <band mbid>, "role": "member" | "supporting"}
    ]
  }
"""

import argparse
import json
import re
import time
import tomllib
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import musicbrainzngs

musicbrainzngs.set_useragent("BandNetworksProject", "0.3", "xabaj68743@inreur.com")

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / "cache"
SCENES_DIR = ROOT / "scenes"
DATA_DIR = ROOT / "data"

RATE_LIMIT_SECONDS = 1.1


def load_scene(name: str) -> dict:
    path = SCENES_DIR / f"{name}.toml"
    if not path.exists():
        raise FileNotFoundError(f"Scene file not found: {path}")
    return tomllib.loads(path.read_text())


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.lower()).strip("_")
    return s or "scene"


def find_existing_by_mbid(mbid: str) -> dict | None:
    """Return the meta of a previously-built single-band scene matching mbid, or None."""
    if not DATA_DIR.exists():
        return None
    try:
        entries = list(DATA_DIR.iterdir())
    except PermissionError:
        return None
    for scene_dir in entries:
        meta_path = scene_dir / "meta.json"
        if not meta_path.exists() or not (scene_dir / "network.json").exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            continue
        if meta.get("kind") == "single-artist" and meta.get("mbid") == mbid:
            return meta
    return None


def search_artist(query: str, limit: int = 5) -> list[dict]:
    """Search MusicBrainz for artists matching `query`. Returns top N candidates."""
    result = musicbrainzngs.search_artists(artist=query, limit=limit)
    return [
        {
            "mbid": a["id"],
            "name": a.get("name", ""),
            "disambiguation": a.get("disambiguation", ""),
            "country": a.get("country", ""),
            "type": a.get("type", ""),
            "score": int(a.get("ext:score", 0)),
        }
        for a in result.get("artist-list", [])
    ]


def _cached_get_artist(mbid: str) -> dict | None:
    """Fetch artist+relationships from MusicBrainz, caching by MBID."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{mbid}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"  ! corrupt MusicBrainz cache for {mbid} ({e}); refetching")
    try:
        result = musicbrainzngs.get_artist_by_id(mbid, includes=["artist-rels"])
    except Exception as e:
        print(f"  ! fetch failed for {mbid}: {e}")
        return None
    cache_file.write_text(json.dumps(result, indent=2))
    time.sleep(RATE_LIMIT_SECONDS)
    return result


def _members_of(artist_data: dict) -> list[tuple[str, str, str]]:
    """Return (musician_id, musician_name, role) tuples; role is 'member' or 'supporting'."""
    out = []
    for rel in artist_data.get("artist-relation-list", []):
        rel_type = rel.get("type", "").lower()
        artist = rel.get("artist") or {}
        if not artist.get("id"):
            continue
        if rel_type in ("member of band", "member"):
            out.append((artist["id"], artist.get("name", "Unknown"), "member"))
        elif rel_type == "supporting musician":
            out.append((artist["id"], artist.get("name", "Unknown"), "supporting"))
    return out


def _bands_of(artist_data: dict) -> list[tuple[str, str]]:
    """Return (band_id, band_name) tuples — bands this musician was a member of
    or supporting musician for. Mirrors the relationship types `_members_of`
    accepts, so a musician's bands list stays symmetric with each band's
    members list."""
    out = []
    for rel in artist_data.get("artist-relation-list", []):
        if rel.get("type", "").lower() not in ("member of band", "member", "supporting musician"):
            continue
        artist = rel.get("artist") or {}
        if artist.get("id"):
            out.append((artist["id"], artist.get("name", "Unknown")))
    return out


def build(
    seeds: list[tuple[str, str]],
    max_depth: int = 1,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Crawl from seed bands, depth-limited, and return a bipartite graph.

    depth 0 = seed bands only.
    depth 1 = seed bands + every band each seed-band-member ever belonged to.

    `progress`, if given, is called after each band is processed with
    {"current": str, "depth": int, "bands_done": int, "musicians_done": int}.
    """
    bands: dict[str, str] = {}
    musicians: dict[str, str] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()

    # A Person seed (e.g. Bob Dylan) is added as a musician; the bands they
    # belong to become the actual BFS seeds. Without this, the BFS would treat
    # the person as a band and their bands as members, inverting the bipartite
    # graph's roles.
    band_seeds: list[tuple[str, str]] = []
    for seed_name, seed_mbid in seeds:
        result = _cached_get_artist(seed_mbid)
        if not result:
            continue
        artist_data = result["artist"]
        if artist_data.get("type", "").lower() != "person":
            band_seeds.append((seed_name, seed_mbid))
            continue
        musicians.setdefault(seed_mbid, artist_data.get("name", seed_name))
        for rel in artist_data.get("artist-relation-list", []):
            rel_type = rel.get("type", "").lower()
            if rel_type in ("member of band", "member"):
                role = "member"
            elif rel_type == "supporting musician":
                role = "supporting"
            else:
                continue
            band = rel.get("artist") or {}
            band_id = band.get("id")
            if not band_id:
                continue
            band_name = band.get("name", "Unknown")
            bands.setdefault(band_id, band_name)
            edge_key = (seed_mbid, band_id, role)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({"source": seed_mbid, "target": band_id, "role": role})
            band_seeds.append((band_name, band_id))

    queue: deque[tuple[str, str, int]] = deque((mbid, name, 0) for name, mbid in band_seeds)
    processed_bands: set[str] = set()

    while queue:
        band_id, band_name, depth = queue.popleft()
        if band_id in processed_bands:
            continue
        processed_bands.add(band_id)
        print(f"[depth {depth}] {band_name}")

        result = _cached_get_artist(band_id)
        if not result:
            continue
        artist_data = result["artist"]
        bands[band_id] = artist_data.get("name", band_name)

        for musician_id, musician_name, role in _members_of(artist_data):
            musicians.setdefault(musician_id, musician_name)
            edge_key = (musician_id, band_id, role)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({"source": musician_id, "target": band_id, "role": role})

            if depth < max_depth:
                m_result = _cached_get_artist(musician_id)
                if not m_result:
                    continue
                for new_band_id, new_band_name in _bands_of(m_result["artist"]):
                    if new_band_id not in processed_bands:
                        queue.append((new_band_id, new_band_name, depth + 1))

        if progress:
            # Total is bands processed + unique bands still queued. The queue
            # grows as BFS discovers new bands, so `total` ratchets up over
            # time but the bar always reflects honest progress.
            pending = {item[0] for item in queue} - processed_bands
            progress({
                "current": band_name,
                "depth": depth,
                "bands_done": len(processed_bands),
                "total": len(processed_bands) + len(pending),
                "musicians_done": len(musicians),
            })

    musician_bands: dict[str, set[str]] = {}
    for e in edges:
        musician_bands.setdefault(e["source"], set()).add(e["target"])
    band_count_per_musician = {m: len(bs) for m, bs in musician_bands.items()}

    nodes = [
        {"id": mbid, "name": name, "type": "band"}
        for mbid, name in bands.items()
    ] + [
        {
            "id": mbid,
            "name": name,
            "type": "musician",
            "band_count": band_count_per_musician.get(mbid, 0),
        }
        for mbid, name in musicians.items()
    ]
    return {"nodes": nodes, "edges": edges}


def write_scene(scene_name: str, graph: dict, meta: dict | None = None) -> Path:
    out_dir = DATA_DIR / scene_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "network.json"
    out_path.write_text(json.dumps(graph, indent=2))
    if meta is not None:
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return out_path


def build_single_artist(
    name: str,
    mbid: str,
    depth: int = 1,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Build a single-artist scene and write data/<slug>/{network,meta}.json.

    Seed may be a band or a person — `build()` handles the dispatch.

    If a scene with this MBID already exists, returns its meta unchanged.
    Otherwise crawls and writes new files. Returns the scene's meta dict.
    Slug collisions with a different MBID get an 8-char MBID suffix.
    """
    existing = find_existing_by_mbid(mbid)
    if existing is not None:
        return existing

    base_slug = slugify(name)
    scene_id = base_slug
    candidate_dir = DATA_DIR / scene_id
    if candidate_dir.exists():
        scene_id = f"{base_slug}_{mbid[:8]}"

    graph = build([(name, mbid)], max_depth=depth, progress=progress)
    n_bands = sum(1 for n in graph["nodes"] if n["type"] == "band")
    n_mus = sum(1 for n in graph["nodes"] if n["type"] == "musician")

    meta = {
        "id": scene_id,
        "name": name,
        "kind": "single-artist",
        "mbid": mbid,
        "depth": depth,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": {"bands": n_bands, "musicians": n_mus, "edges": len(graph["edges"])},
    }
    write_scene(scene_id, graph, meta=meta)
    return meta


def main():
    parser = argparse.ArgumentParser(description="Build a band-network graph from MusicBrainz.")
    parser.add_argument("--scene", default="grunge", help="Scene name (file in scenes/<name>.toml).")
    parser.add_argument(
        "--band",
        help="Build a single-band scene by artist name (overrides --scene seeds, looks up MBID via MusicBrainz search).",
    )
    parser.add_argument("--depth", type=int, help="Override max_depth for this run.")
    args = parser.parse_args()

    if args.band:
        candidates = search_artist(args.band, limit=1)
        if not candidates:
            raise SystemExit(f"No MusicBrainz match for '{args.band}'.")
        top = candidates[0]
        depth = args.depth if args.depth is not None else 1
        print(f"Building single-band scene from {top['name']} ({top['mbid']}), depth {depth}")
        meta = build_single_artist(top["name"], top["mbid"], depth=depth)
        scene_id = meta["id"]
        out_path = DATA_DIR / scene_id / "network.json"
        stats = meta["stats"]
        print(f"\nWrote {out_path}: {stats['bands']} bands, {stats['musicians']} musicians, {stats['edges']} edges.")
        return

    scene = load_scene(args.scene)
    scene_name = args.scene
    seeds = [(s["name"], s["mbid"]) for s in scene["seeds"]]
    depth = args.depth if args.depth is not None else scene.get("max_depth", 1)
    print(f"Building scene '{scene_name}' ({scene.get('name', scene_name)}) with {len(seeds)} seeds, depth {depth}")

    graph = build(seeds, max_depth=depth)
    n_bands = sum(1 for n in graph["nodes"] if n["type"] == "band")
    n_mus = sum(1 for n in graph["nodes"] if n["type"] == "musician")
    meta = {
        "id": scene_name,
        "name": scene.get("name", scene_name),
        "kind": "scene",
        "mbid": None,
        "depth": depth,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": {"bands": n_bands, "musicians": n_mus, "edges": len(graph["edges"])},
    }
    out_path = write_scene(scene_name, graph, meta=meta)
    print(f"\nWrote {out_path}: {n_bands} bands, {n_mus} musicians, {len(graph['edges'])} edges.")


if __name__ == "__main__":
    main()
