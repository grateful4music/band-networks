"""FastAPI server for the band-networks viz.

Serves the static index.html, the per-scene data files, and a small JSON API
for listing available scenes. Stage 3 will add /api/search and /api/build.

Run:
    uv run server.py
    # or with auto-reload:
    uv run uvicorn server:app --reload --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SCENES_DIR = ROOT / "scenes"
INDEX_HTML = ROOT / "index.html"

app = FastAPI(title="band-networks", version="0.3")


def _scene_meta(scene_id: str) -> dict | None:
    """Read a scene's metadata + stats from data/<scene_id>/network.json (and the
    matching scenes/<scene_id>.toml if present). Returns None if the network is
    missing or unreadable."""
    network_path = DATA_DIR / scene_id / "network.json"
    if not network_path.exists():
        return None

    meta: dict = {"id": scene_id, "name": scene_id, "description": ""}
    toml_path = SCENES_DIR / f"{scene_id}.toml"
    if toml_path.exists():
        try:
            t = tomllib.loads(toml_path.read_text())
            meta["name"] = t.get("name", scene_id)
            meta["description"] = t.get("description", "")
        except tomllib.TOMLDecodeError:
            pass

    try:
        graph = json.loads(network_path.read_text())
        n_bands = sum(1 for n in graph["nodes"] if n["type"] == "band")
        n_mus = sum(1 for n in graph["nodes"] if n["type"] == "musician")
        meta["stats"] = {
            "bands": n_bands,
            "musicians": n_mus,
            "edges": len(graph["edges"]),
        }
    except (OSError, json.JSONDecodeError, KeyError):
        return None

    meta["has_popularity"] = (DATA_DIR / scene_id / "popularity.json").exists()
    return meta


@app.get("/api/scenes")
def list_scenes():
    if not DATA_DIR.exists():
        return {"scenes": []}
    out = []
    for scene_dir in sorted(DATA_DIR.iterdir()):
        if not scene_dir.is_dir():
            continue
        meta = _scene_meta(scene_dir.name)
        if meta is not None:
            out.append(meta)
    return {"scenes": out}


@app.get("/")
def index():
    return FileResponse(INDEX_HTML)


# Mount /data after specific routes so /api/* and / take precedence.
app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


def main():
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=True)


if __name__ == "__main__":
    main()
