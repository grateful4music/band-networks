"""Fetch Seattle grunge band/musician data from MusicBrainz and emit a bipartite graph.

Output schema (bands_network.json):
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

import json
import time
from pathlib import Path

import musicbrainzngs

# TODO: replace with a real contact email — MusicBrainz TOS requires it.
musicbrainzngs.set_useragent("GrungeMappingProject", "0.2", "your-email@example.com")

CACHE_DIR = Path(__file__).parent / "cache"
OUTPUT_PATH = Path(__file__).parent / "bands_network.json"

# Curated seed list of canonical Seattle grunge bands.
# MBIDs verified against the existing bands_raw.json crawl.
# Bands without an MBID need lookup via MusicBrainz search before they can be included.
CANONICAL_SEEDS = [
    ("Mother Love Bone",  "a5585acd-9b65-49a7-a63b-3cc4ee18846e"),
    ("Pearl Jam",         "83b9cbe7-9857-49e2-ab8e-b57b01038103"),
    ("Nirvana",           "5b11f4ce-a62d-471e-81fc-a69a8278c7da"),
    ("Soundgarden",       "153c9281-268f-4cf3-8938-f5a4593e5df4"),
    ("Mudhoney",          "e675295a-1efe-4247-aa3b-53b78d0cdffc"),
    ("Green River",       "78f56916-fe11-4110-8f10-d553ddf8de7b"),
    ("Temple of the Dog", "e9571c17-817f-4d34-ae3f-0c7a96f822c1"),
    ("Mad Season",        "bfd085b8-0bbf-46b3-8ab9-193bca5c85e7"),
    ("Screaming Trees",   "bc5e6e42-73ba-44fa-a41e-3379402f0429"),
    ("Skin Yard",         "0119843b-4d56-47b6-ac0d-11528259bf0a"),
    ("Malfunkshun",       "71f4a8ff-97ba-47c6-a729-7f87de77c796"),
    ("Love Battery",      "20fa3e73-7ac4-4550-b9f5-6ac8c523bda5"),
    # TODO: look up MBIDs for: Alice in Chains, Melvins, Tad, 7 Year Bitch,
    # Hole, Foo Fighters, The Fastbacks, Gas Huffer.
]

RATE_LIMIT_SECONDS = 1.1


def _cached_get_artist(mbid: str) -> dict | None:
    """Fetch artist+relationships from MusicBrainz, caching by MBID."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{mbid}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
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
    """Return (band_id, band_name) tuples — bands this musician was a member of."""
    out = []
    for rel in artist_data.get("artist-relation-list", []):
        if rel.get("type", "").lower() not in ("member of band", "member"):
            continue
        artist = rel.get("artist") or {}
        if artist.get("id"):
            out.append((artist["id"], artist.get("name", "Unknown")))
    return out


def build(seeds: list[tuple[str, str]], max_depth: int = 1) -> dict:
    """Crawl from seed bands, depth-limited, and return a bipartite graph.

    depth 0 = seed bands only.
    depth 1 = seed bands + every band each seed-band-member ever belonged to.
    """
    bands: dict[str, str] = {}
    musicians: dict[str, str] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()

    queue = [(mbid, name, 0) for name, mbid in seeds]
    processed_bands: set[str] = set()

    while queue:
        band_id, band_name, depth = queue.pop(0)
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

    band_count_per_musician: dict[str, int] = {}
    for e in edges:
        band_count_per_musician[e["source"]] = band_count_per_musician.get(e["source"], 0) + 1

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


def main():
    graph = build(CANONICAL_SEEDS, max_depth=1)
    OUTPUT_PATH.write_text(json.dumps(graph, indent=2))
    n_bands = sum(1 for n in graph["nodes"] if n["type"] == "band")
    n_mus = sum(1 for n in graph["nodes"] if n["type"] == "musician")
    print(f"\nWrote {OUTPUT_PATH.name}: {n_bands} bands, {n_mus} musicians, {len(graph['edges'])} edges.")


if __name__ == "__main__":
    main()
