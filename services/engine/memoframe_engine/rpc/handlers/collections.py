"""RPC handlers for duplicate clusters, burst sequences, and chronological timeline groups."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from memoframe_engine.rpc.handlers.library import enrich_photos


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
                result.append(
                    {
                        "cluster_id": str(cid),
                        "kind": str(enriched[0].get("kind", "near")),
                        "best_image_id": best_id,
                        "photos": enriched,
                    }
                )
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
            for item in eng.get_burst_images(burst_id) or []:
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

    def _parse_utc_epoch(raw_ts: Any) -> tuple[bool, float, str | None]:
        if not raw_ts:
            return (False, 0.0, None)
        s = str(raw_ts).strip()
        if not s:
            return (False, 0.0, None)
        # Normalize EXIF "YYYY:MM:DD HH:MM:SS" and trailing Z
        if len(s) >= 10 and s[4] == ":" and s[7] == ":":
            s = s[:4] + "-" + s[5:7] + "-" + s[8:]
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            try:
                dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return (False, 0.0, None)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return (True, dt.timestamp(), dt.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def timeline_groups(params: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, min(100, int(params.get("limit") or 20)))
        offset = max(0, int(params.get("offset") or 0))
        preview_limit = max(1, min(16, int(params.get("preview_limit") or 8)))
        order = str(params.get("order") or "desc").lower()
        date_from = str(params.get("date_from") or "").strip()
        date_to = str(params.get("date_to") or "").strip()
        search = str(params.get("search") or "").strip().lower()
        ok_from, from_epoch, _ = _parse_utc_epoch(f"{date_from}T00:00:00Z") if date_from else (False, 0.0, None)
        ok_to, to_epoch, _ = _parse_utc_epoch(f"{date_to}T23:59:59Z") if date_to else (False, 0.0, None)

        eng = ctx.require_engine()
        with ctx.lock:
            groups = list(eng.get_groups() or [])
            seen_ids: set[int] = set()
            dated: list[tuple[float, int, dict[str, Any]]] = []
            undated: list[tuple[int, dict[str, Any]]] = []
            for g in groups:
                gid = int(g["id"])
                if gid in seen_ids:
                    continue
                seen_ids.add(gid)
                name_str = str(g.get("name") or f"Event #{gid}")
                if search and search not in name_str.lower():
                    continue
                g_copy = dict(g)
                valid_s, epoch_s, iso_s = _parse_utc_epoch(g.get("start_ts"))
                valid_e, _epoch_e, iso_e = _parse_utc_epoch(g.get("end_ts"))
                g_copy["start_ts_utc"] = iso_s
                g_copy["end_ts_utc"] = iso_e
                g_copy["timestamp_valid"] = valid_s
                if valid_s:
                    if ok_from and epoch_s < from_epoch:
                        continue
                    if ok_to and epoch_s > to_epoch:
                        continue
                    dated.append((epoch_s, gid, g_copy))
                else:
                    if ok_from or ok_to:
                        continue
                    undated.append((gid, g_copy))

            dated.sort(key=lambda item: (item[0], item[1]), reverse=(order != "asc"))
            undated.sort(key=lambda item: item[0], reverse=True)
            ordered = [item[2] for item in dated] + [item[1] for item in undated]
            page_groups = ordered[offset : offset + limit]
            enriched_groups: list[dict[str, Any]] = []
            for g_copy in page_groups:
                raw_photos = eng.get_group_images(int(g_copy["id"]), limit=preview_limit) or []
                g_copy["photos"] = enrich_photos(eng, raw_photos, include_thumbs=True)
                enriched_groups.append(g_copy)
        return {
            "groups": enriched_groups,
            "total": len(ordered),
            "offset": offset,
            "limit": limit,
            "order": "asc" if order == "asc" else "desc",
        }

    registry.update(
        {
            "duplicates.list": duplicates_list,
            "duplicates.resolve": duplicates_resolve,
            "bursts.list": bursts_list,
            "bursts.frames": bursts_frames,
            "bursts.keep_one": bursts_keep_one,
            "bursts.keep_all": bursts_keep_all,
            "timeline.groups": timeline_groups,
        }
    )
