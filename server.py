"""FastAPI server for the band-networks viz.

Routes:
  GET  /                      — index.html
  GET  /api/scenes            — list available scenes (data/<id>/network.json)
  GET  /api/search?q=&limit=  — MusicBrainz artist search
  POST /api/build             — start (or skip) a single-band crawl
  GET  /api/build/{job_id}    — poll a build job
  GET  /data/...              — static scene data files

Run:
    uv run server.py
"""

from __future__ import annotations

import json
import os
import threading
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env (e.g. LASTFM_API_KEY) before importing modules that read env at import time.
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from build_network import build_single_artist, find_existing_by_mbid, search_artist
from fetch_popularity import fetch_popularity_for_scene

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SCENES_DIR = ROOT / "scenes"
INDEX_HTML = ROOT / "index.html"

app = FastAPI(title="band-networks", version="0.3")

# In-memory job tracker. Lost on restart — fine for a personal tool.
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
MAX_JOBS = 50  # cap retained jobs; oldest finished ones get evicted

# Cache MusicBrainz search results per query so rapid typing doesn't refetch.
_SEARCH_CACHE: dict[str, list[dict]] = {}
MAX_SEARCH_CACHE = 200


def _evict_old_jobs() -> None:
    """Evict the oldest finished jobs until JOBS is at or under MAX_JOBS. Called
    while holding JOBS_LOCK. Running/queued jobs are never evicted."""
    while len(JOBS) > MAX_JOBS:
        for jid, job in JOBS.items():
            if job.get("state") in ("done", "error"):
                del JOBS[jid]
                break
        else:
            return  # nothing finished to evict


def _scene_meta(scene_id: str) -> dict | None:
    """Read a scene's metadata. Prefers data/<id>/meta.json (new builds), falls
    back to the matching scenes/<id>.toml (legacy scenes built before meta.json
    existed). Returns None if no network.json is present."""
    network_path = DATA_DIR / scene_id / "network.json"
    if not network_path.exists():
        return None

    meta_path = DATA_DIR / scene_id / "meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            pass

    # Fallback: synthesize from network.json (+ TOML if available)
    meta: dict = {
        "id": scene_id,
        "name": scene_id,
        "kind": "scene",
        "mbid": None,
        "depth": None,
        "built_at": None,
    }
    toml_path = SCENES_DIR / f"{scene_id}.toml"
    if toml_path.exists():
        try:
            t = tomllib.loads(toml_path.read_text())
            meta["name"] = t.get("name", scene_id)
            meta["description"] = t.get("description", "")
            meta["depth"] = t.get("max_depth")
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
            meta["has_popularity"] = (scene_dir / "popularity.json").exists()
            out.append(meta)
    return {"scenes": out}


@app.get("/api/search")
def search(q: str, limit: int = 5):
    q = q.strip()
    if not q:
        return {"results": []}
    key = f"{q.lower()}::{limit}"
    if key in _SEARCH_CACHE:
        return {"results": _SEARCH_CACHE[key]}
    try:
        results = search_artist(q, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MusicBrainz search failed: {e}")
    if len(_SEARCH_CACHE) >= MAX_SEARCH_CACHE:
        _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))  # FIFO eviction
    _SEARCH_CACHE[key] = results
    return {"results": results}


class BuildRequest(BaseModel):
    name: str = Field(min_length=1)
    mbid: str = Field(min_length=8)
    depth: int = Field(default=1, ge=0, le=3)
    force: bool = False


def _run_build_job(job_id: str, name: str, mbid: str, depth: int) -> None:
    def mb_progress(info: dict) -> None:
        with JOBS_LOCK:
            JOBS[job_id].update({
                "state": "running",
                "phase": "musicbrainz",
                "progress": info,
            })

    def lf_progress(info: dict) -> None:
        with JOBS_LOCK:
            JOBS[job_id].update({
                "state": "running",
                "phase": "lastfm",
                "progress": info,
            })

    try:
        with JOBS_LOCK:
            JOBS[job_id]["state"] = "running"
            JOBS[job_id]["phase"] = "musicbrainz"
            JOBS[job_id]["started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        meta = build_single_artist(name, mbid, depth=depth, progress=mb_progress)
        scene_id = meta["id"]

        # Phase 2: fetch popularity if a Last.fm key is configured.
        if os.environ.get("LASTFM_API_KEY"):
            try:
                fetch_popularity_for_scene(scene_id, progress=lf_progress)
            except Exception as e:
                # Don't fail the build over popularity — record a warning.
                with JOBS_LOCK:
                    JOBS[job_id]["popularity_warning"] = f"{type(e).__name__}: {e}"

        with JOBS_LOCK:
            JOBS[job_id].update({
                "state": "done",
                "phase": "done",
                "scene_id": scene_id,
                "meta": meta,
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update({
                "state": "error",
                "error": f"{type(e).__name__}: {e}",
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })


@app.post("/api/build")
def build_endpoint(req: BuildRequest):
    if not req.force:
        existing = find_existing_by_mbid(req.mbid)
        if existing is not None:
            return {"status": "exists", "scene_id": existing["id"], "meta": existing}

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "state": "queued",
            "name": req.name,
            "mbid": req.mbid,
            "depth": req.depth,
            "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _evict_old_jobs()
    threading.Thread(
        target=_run_build_job,
        args=(job_id, req.name, req.mbid, req.depth),
        daemon=True,
        name=f"build-{job_id}",
    ).start()
    return {"status": "building", "job_id": job_id}


@app.get("/api/build/{job_id}")
def build_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return dict(job)


@app.get("/api/config")
def get_config():
    return {"lastfm_enabled": bool(os.environ.get("LASTFM_API_KEY"))}


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
