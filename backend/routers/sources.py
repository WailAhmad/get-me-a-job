"""
Job source connections.

These endpoints keep a product-grade connection model in place while each
board-specific browser/OAuth flow is implemented. LinkedIn still uses the
separate automation session endpoints because it needs a browser profile.
"""
import time
from fastapi import APIRouter, HTTPException

from backend import state

router = APIRouter(prefix="/sources", tags=["sources"])


def _sources():
    current = state.get().setdefault("job_sources", {})
    defaults = state.DEFAULT["job_sources"]
    changed = False
    for source_id, source in defaults.items():
        if source_id not in current:
            current[source_id] = dict(source)
            changed = True
        else:
            for key, value in source.items():
                if key not in current[source_id]:
                    current[source_id][key] = value
                    changed = True
    if changed:
        state.save()
    return current


@router.get("/")
def list_sources():
    sources = _sources()
    linkedin_session = state.get().get("settings", {}).get("linkedin_session_active", False)
    items = []
    for source in sources.values():
        item = dict(source)
        if item["id"] == "linkedin":
            item["connected"] = bool(item.get("connected") or linkedin_session)
        items.append(item)
    return {"sources": sorted(items, key=lambda s: (s["region"], s["name"]))}


@router.post("/{source_id}/connect")
def connect_source(source_id: str):
    sources = _sources()
    if source_id not in sources:
        raise HTTPException(404, "Unknown job source.")
    if source_id != "linkedin":
        raise HTTPException(
            501,
            f"{sources[source_id]['name']} is not wired to a real connection flow yet. No fake connector was created.",
        )

    def m(s):
        source = s.setdefault("job_sources", {}).setdefault(source_id, {})
        source["connected"] = True
        source["connected_at"] = time.time()

    state.update(m)
    source = state.get()["job_sources"][source_id]
    return {"success": True, "source": source, "message": f"{source['name']} connected using the real LinkedIn browser session."}


@router.delete("/{source_id}")
def disconnect_source(source_id: str):
    sources = _sources()
    if source_id not in sources:
        raise HTTPException(404, "Unknown job source.")

    def m(s):
        source = s.setdefault("job_sources", {}).setdefault(source_id, {})
        source["connected"] = False
        source["connected_at"] = None
        source.pop("mock", None)

    state.update(m)
    return {"success": True}
