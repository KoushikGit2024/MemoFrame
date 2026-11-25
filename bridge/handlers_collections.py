"""RPC handlers for duplicate clusters, burst sequences, and chronological timeline groups."""
from __future__ import annotations

from typing import Any

from bridge.handlers_library import enrich_photos


def register_collection_handlers(registry: dict[str, Any], ctx: Any) -> None:
    """Register duplicates, bursts, and timeline RPC handlers."""

    def duplicates_list(_params: dict[str, Any]) -> list[dict[str, Any]]:
        eng = ctx.require_engine()
        with ctx.lock:
            clusters_map = eng.get_duplicate_clusters() or {}
            result: list[dict[str, Any]] = []
            for cid, members in clusters_map.items():
                if len(members) <= 1:
                    continue
                enriched = enrich_photos(eng, members, include_thumbs=True)
                best_id = next(
                    (int(p["id"]) for p in enriched if p.get("suggested_keep")),
                    int(enriched[0]["id"]),
                )
                result.append({
                    "cluster_id": str(cid),
                    "kind": str(enriched[0].get("kind", "near")),
                    "best_image_id": best_id,
                    "photos": enriched,
                })
        return result

    def duplicates_resolve(params: dict[str, Any]) -> dict[str, Any]:
        keep_id = int(params["keep_id"])
        hide_ids = [int(pid) for pid in (params.get("hide_ids") or []) if int(pid) != keep_id]
        eng = ctx.require_engine()
        with ctx.lock:
            eng.set_mark(keep_id, "keep")
            for pid in hide_ids:
                eng.set_mark(pid, "hidden")
        return {"keep_id": keep_id, "hidden_count": len(hide_ids)}

    def bursts_list(_params: dict[str, Any]) -> list[dict[str, Any]]:
        eng = ctx.require_engine()
        with ctx.lock:
            hidden = {int(m["image_id"]) for m in (eng.get_marks(None, "hidden") or [])}
            kept = {int(m["image_id"]) for m in (eng.get_marks(None, "keep") or [])}
            resolved = hidden | kept
            raw = eng.get_bursts() or []
            bursts = [
                dict(b)
                for b in raw
                if int(b.get("image_count", 0)) > 1 and b.get("best_image_id") not in resolved
            ]
        return bursts

    def bursts_frames(params: dict[str, Any]) -> list[dict[str, Any]]:
        burst_id = int(params["burst_id"])
        best_id = params.get("best_image_id")
        eng = ctx.require_engine()
        with ctx.lock:
            hidden = {int(m["image_id"]) for m in (eng.get_marks(None, "hidden") or [])}
            frames: list[dict[str, Any]] = []
            for item in (eng.get_burst_images(burst_id) or []):
                if item.get("state") == "missing" or int(item["id"]) in hidden:
                    continue
                frame = dict(item)
                frame["suggested"] = best_id is not None and int(frame["id"]) == int(best_id)
                try:
                    frame["thumb_path"] = eng.thumbnail(int(frame["id"]))
                except Exception:
                    frame["thumb_path"] = None
                frames.append(frame)
        return frames

    def bursts_keep_one(params: dict[str, Any]) -> dict[str, Any]:
        keep_id = int(params["keep_id"])
        hide_ids = [int(pid) for pid in (params.get("hide_ids") or []) if int(pid) != keep_id]
        eng = ctx.require_engine()
        with ctx.lock:
            eng.set_mark(keep_id, "keep")
            for pid in hide_ids:
                eng.set_mark(pid, "hidden")
        return {"keep_id": keep_id, "hidden_count": len(hide_ids)}

    def bursts_keep_all(params: dict[str, Any]) -> dict[str, Any]:
        best_id = int(params["best_image_id"])
        eng = ctx.require_engine()
        with ctx.lock:
            eng.set_mark(best_id, "keep")
        return {"best_image_id": best_id}

    def timeline_groups(params: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, min(100, int(params.get("limit") or 20)))
        offset = max(0, int(params.get("offset") or 0))
        preview_limit = max(1, min(16, int(params.get("preview_limit") or 8)))
        eng = ctx.require_engine()
        with ctx.lock:
            groups = list(eng.get_groups() or [])
            dated = sorted((g for g in groups if g.get("start_ts")), key=lambda g: g["start_ts"], reverse=True)
            ordered = dated + [g for g in groups if not g.get("start_ts")]
            page_groups = ordered[offset:offset + limit]
            enriched_groups: list[dict[str, Any]] = []
            for g in page_groups:
                g_copy = dict(g)
                raw_photos = eng.get_group_images(int(g["id"]), limit=preview_limit) or []
                g_copy["photos"] = enrich_photos(eng, raw_photos, include_thumbs=True)
                enriched_groups.append(g_copy)
        return {"groups": enriched_groups, "total": len(ordered), "offset": offset, "limit": limit}

    registry.update({
        "duplicates.list": duplicates_list,
        "duplicates.resolve": duplicates_resolve,
        "bursts.list": bursts_list,
        "bursts.frames": bursts_frames,
        "bursts.keep_one": bursts_keep_one,
        "bursts.keep_all": bursts_keep_all,
        "timeline.groups": timeline_groups,
    })
