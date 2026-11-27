"""RPC handlers for photo library queries, detail inspection, marks, dates, tags, and search."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import io
import shutil
from pathlib import Path
from typing import Any, Sequence


def ensure_face_crop(
    workspace: Path, face: dict[str, Any], img_path: str | None, size: int = 320
) -> str | None:
    """Generate a crisp square face crop (Lanczos resampled) centered on the face with proportional margin.

    Caches to workspace/face_crops/face_{face_id}_{size}.jpg to make grid face zoom instant.
    """
    fid = face.get("id")
    if not fid:
        return None

    crop_dir = workspace / "face_crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    out_path = crop_dir / f"crop_face_{fid}_{size}.jpg"
    if out_path.is_file():
        return str(out_path)

    # Check if face already has an existing valid crop on disk
    existing = face.get("crop_path")
    if existing:
        ep = Path(str(existing))
        if not ep.is_absolute():
            ep = (
                (workspace.parent / ep).resolve()
                if (workspace.parent / ep).is_file()
                else (workspace / ep).resolve()
            )
        if ep.is_file():
            # If size matches or existing is already a square crop, we can use it
            return str(ep)

    if not img_path or not Path(str(img_path)).is_file():
        return None

    w = face.get("w")
    h = face.get("h")
    if not w or not h or int(w) <= 0 or int(h) <= 0:
        return None

    try:
        from PIL import Image, ImageOps

        with Image.open(str(img_path)) as raw_im:
            im = ImageOps.exif_transpose(raw_im).convert("RGB")
            xi, yi, wi, hi = int(face.get("x") or 0), int(face.get("y") or 0), int(w), int(h)

            # Balanced square box with ~27.5% padding around head/chin
            side = int(max(wi, hi) * 1.55)
            side = min(side, im.width, im.height)
            cx = xi + wi // 2
            cy = yi + hi // 2

            left = max(0, min(im.width - side, cx - side // 2))
            top = max(0, min(im.height - side, cy - side // 2))

            crop = im.crop((left, top, left + side, top + side))
            crop = crop.resize((size, size), Image.Resampling.LANCZOS)
            crop.save(str(out_path), "JPEG", quality=92, optimize=True)
            return str(out_path)
    except Exception:
        return None


def enrich_photos(
    engine: Any,
    items: Sequence[dict[str, Any]],
    include_thumbs: bool = True,
    target_person_id: int | None = None,
    workspace: Path | None = None,
    unassigned_only: bool = False,
) -> list[dict[str, Any]]:
    """Attach faces (single batch query), thumbnail paths, and pre-generated square face crops to photo records."""
    if not items:
        return []
    ids = [int(p["id"]) for p in items if "id" in p]
    faces_by_img: dict[int, list[dict[str, Any]]] = {}
    if ids:
        try:
            faces_by_img = engine.get_faces_many(ids) or {}
        except Exception:
            faces_by_img = {}

    enriched: list[dict[str, Any]] = []
    for p in items:
        pid = int(p.get("id", 0))
        row = dict(p)
        img_faces = faces_by_img.get(pid, faces_by_img.get(str(pid), []))
        row["faces"] = img_faces

        # Resolve thumbnail
        if include_thumbs and pid:
            try:
                row["thumb_path"] = engine.thumbnail(pid)
            except Exception:
                row["thumb_path"] = None

        # Resolve square face crop for face-zoom mode
        if workspace and img_faces:
            target_face = None
            if target_person_id is not None:
                target_face = next(
                    (f for f in img_faces if f.get("person_id") == target_person_id), None
                )
            elif unassigned_only:
                unassigned = [f for f in img_faces if f.get("person_id") is None]
                if unassigned:
                    target_face = max(
                        unassigned, key=lambda f: int(f.get("w", 0)) * int(f.get("h", 0))
                    )
            if not target_face:
                target_face = max(img_faces, key=lambda f: int(f.get("w", 0)) * int(f.get("h", 0)))
            if target_face:
                crop = ensure_face_crop(
                    workspace, target_face, str(row.get("path") or ""), size=320
                )
                row["face_crop_path"] = crop
            else:
                row["face_crop_path"] = None
        else:
            row["face_crop_path"] = None

        enriched.append(row)
    return enriched


def register_library_handlers(registry: dict[str, Any], ctx: Any) -> None:
    """Register photo gallery, inspector, mark, date, tag, and saved-search RPC handlers."""

    def photos_query(params: dict[str, Any]) -> dict[str, Any]:
        filters = dict(params.get("filters") or {})
        sort = str(params.get("sort") or "date_desc")
        page = max(0, int(params.get("page") or 0))
        size = max(1, min(200, int(params.get("page_size") or 40)))
        eng = ctx.require_engine()
        with ctx.lock:
            gone = (
                filters.get("person_id") is not None
                and eng.get_person(int(filters["person_id"])) is None
            )
            if gone:
                filters.pop("person_id", None)
            total = int(eng.count(kind="photo", **filters))
            pages = max(1, (total + size - 1) // size)
            page = min(page, pages - 1)
            raw_items = eng.find(kind="photo", sort=sort, limit=size, offset=page * size, **filters)
            target_pid = int(filters["person_id"]) if filters.get("person_id") is not None else None
            items = enrich_photos(
                eng,
                raw_items,
                include_thumbs=True,
                target_person_id=target_pid,
                workspace=ctx.workspace,
                unassigned_only=bool(filters.get("unassigned_faces")),
            )
        return {"items": items, "total": total, "pages": pages, "page": page, "person_gone": gone}

    def photo_detail(params: dict[str, Any]) -> dict[str, Any]:
        image_id = int(params["image_id"])
        eng = ctx.require_engine()
        with ctx.lock:
            row = eng.get_image(image_id) or {}
            faces_map = eng.get_faces_many([image_id]) or {}
            faces = faces_map.get(image_id, faces_map.get(str(image_id), []))
            tags = eng.get_tags(image_id) or []
            marks = [m["kind"] for m in (eng.get_marks(image_id) or [])]
            live = eng.live_video(image_id)
            thumb = None
            try:
                thumb = eng.thumbnail(image_id)
            except Exception:
                pass
        live_valid = bool(live and Path(str(live.get("path", ""))).is_file())
        return {
            "photo": dict(row),
            "faces": faces,
            "tags": tags,
            "marks": marks,
            "live_video": live if live_valid else None,
            "thumb_path": thumb,
        }

    def photo_toggle_mark(params: dict[str, Any]) -> dict[str, Any]:
        image_id = int(params["image_id"])
        kind = str(params["kind"])
        eng = ctx.require_engine()
        with ctx.lock:
            current = {m["kind"] for m in (eng.get_marks(image_id) or [])}
            if kind in current:
                eng.clear_mark(image_id, kind)
                active = False
            else:
                eng.set_mark(image_id, kind)
                active = True
            updated = [m["kind"] for m in (eng.get_marks(image_id) or [])]
        return {"active": active, "marks": updated}

    def photo_set_date(params: dict[str, Any]) -> dict[str, Any]:
        image_id = int(params["image_id"])
        iso = str(params["iso"])
        reason = str(params.get("reason") or "manual (lightbox)")
        eng = ctx.require_engine()
        with ctx.lock:
            eng.set_date_override(image_id, iso, reason)
        return {"image_id": image_id, "effective_ts": iso}

    def photo_clear_date(params: dict[str, Any]) -> dict[str, Any]:
        image_id = int(params["image_id"])
        eng = ctx.require_engine()
        with ctx.lock:
            eng.clear_date_override(image_id)
            row = eng.get_image(image_id) or {}
        return {"image_id": image_id, "effective_ts": row.get("exif_ts")}

    def photos_similar(params: dict[str, Any]) -> list[dict[str, Any]]:
        image_id = int(params["image_id"])
        limit = int(params.get("limit") or 24)
        eng = ctx.require_engine()
        with ctx.lock:
            items = eng.similar(image_id, limit) or []
            return enrich_photos(eng, items, include_thumbs=True)

    def photos_failed(params: dict[str, Any]) -> list[dict[str, Any]]:
        limit = int(params.get("limit") or 500)
        eng = ctx.require_engine()
        with ctx.lock:
            if hasattr(eng, "failed_images") and callable(eng.failed_images):
                rows = list(eng.failed_images() or [])
            else:
                rows = list(eng.find(status="failed", limit=limit) or [])
            return rows[:limit]

    def dates_suspicious(params: dict[str, Any]) -> list[dict[str, Any]]:
        limit = int(params.get("limit") or 500)
        eng = ctx.require_engine()
        with ctx.lock:
            return list(eng.suspicious_dates(limit) or [])

    def tags_list(params: dict[str, Any]) -> list[dict[str, Any]]:
        limit = int(params.get("limit") or 80)
        eng = ctx.require_engine()
        with ctx.lock:
            return list(eng.list_tags(limit) or [])

    def saved_searches_list(_params: dict[str, Any]) -> list[dict[str, Any]]:
        eng = ctx.require_engine()
        with ctx.lock:
            return list(eng.list_saved_searches() or [])

    def saved_searches_save(params: dict[str, Any]) -> dict[str, Any]:
        name = str(params["name"]).strip()
        filters = dict(params.get("filters") or {})
        eng = ctx.require_engine()
        with ctx.lock:
            eng.save_search(name, filters)
        return {"saved": name}

    def saved_searches_delete(params: dict[str, Any]) -> dict[str, Any]:
        name = str(params["name"])
        eng = ctx.require_engine()
        with ctx.lock:
            eng.delete_saved_search(name)
        return {"deleted": name}

    def photo_decode(params: dict[str, Any]) -> dict[str, Any]:
        """Decode non-browser-native formats (e.g. HEIC/TIFF) via Pillow to JPEG data URL."""
        path = Path(str(params["path"]))
        max_side = max(256, min(4096, int(params.get("max_side") or 2400)))
        if not path.is_file():
            return {"data_url": None}
        try:
            import memoframe_engine.domains.media.loader  # noqa: F401
        except Exception:
            pass
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return {
                "data_url": f"data:image/jpeg;base64,{b64}",
                "width": im.width,
                "height": im.height,
            }


    def _unique_dest(dest_dir: Path, stem: str, ext: str) -> Path:
        cand = dest_dir / f"{stem}{ext}"
        idx = 1
        while cand.exists():
            cand = dest_dir / f"{stem} ({idx}){ext}"
            idx += 1
        return cand

    def photos_export(params: dict[str, Any]) -> dict[str, Any]:
        """Non-destructively export selected photos (original copy or resized JPEG/PNG/WebP)."""
        raw_ids = params.get("image_ids") or []
        dest_str = str(params.get("dest_dir") or "").strip()
        fmt = str(params.get("format") or "original").lower()
        quality = max(60, min(100, int(params.get("quality") or 92)))
        raw_max_side = params.get("max_side")
        max_side = int(raw_max_side) if raw_max_side not in (None, "", 0, "0") else None
        strip_metadata = bool(params.get("strip_metadata", False))

        if not dest_str:
            raise ValueError("Destination folder is required.")
        dest_dir = Path(dest_str).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        eng = ctx.require_engine()
        sources: list[tuple[int, Path]] = []
        with ctx.lock:
            for raw_id in raw_ids:
                iid = int(raw_id)
                row = eng.get_image(iid)
                if row and row.get("path"):
                    p = Path(str(row["path"]))
                    if p.is_file():
                        sources.append((iid, p))

        if not sources:
            return {"exported": 0, "failed": 0, "dest_dir": str(dest_dir), "files": []}

        ext_map = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "webp": ".webp"}
        pil_fmt = {"jpeg": "JPEG", "jpg": "JPEG", "png": "PNG", "webp": "WEBP"}
        import threading
        name_lock = threading.Lock()

        def _export_one(item: tuple[int, Path]) -> tuple[bool, str]:
            _iid, src = item
            try:
                if fmt == "original" and not max_side and not strip_metadata:
                    with name_lock:
                        out_path = _unique_dest(dest_dir, src.stem, src.suffix or ".jpg")
                        out_path.touch()
                    shutil.copy2(src, out_path)
                    return True, str(out_path)

                try:
                    import memoframe_engine.domains.media.loader  # noqa: F401
                except Exception:
                    pass
                from PIL import Image, ImageOps

                target_ext = ext_map.get(fmt, ".jpg")
                save_fmt = pil_fmt.get(fmt, "JPEG")
                with name_lock:
                    out_path = _unique_dest(dest_dir, src.stem, target_ext)
                    out_path.touch()

                with Image.open(src) as im:
                    im = ImageOps.exif_transpose(im)
                    if save_fmt == "JPEG" and im.mode not in ("RGB", "L"):
                        im = im.convert("RGB")
                    if max_side and max_side >= 256:
                        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                    save_kwargs: dict[str, Any] = {}
                    if save_fmt in ("JPEG", "WEBP"):
                        save_kwargs["quality"] = quality
                    if save_fmt == "JPEG":
                        save_kwargs["optimize"] = True
                    if not strip_metadata and "exif" in im.info and save_fmt in ("JPEG", "WEBP"):
                        save_kwargs["exif"] = im.info["exif"]
                    im.save(out_path, format=save_fmt, **save_kwargs)
                return True, str(out_path)
            except Exception as exc:
                return False, f"{src.name}: {exc}"

        exported_files: list[str] = []
        failed_msgs: list[str] = []
        workers = min(4, max(1, len(sources)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for ok, info in pool.map(_export_one, sources):
                if ok:
                    exported_files.append(info)
                else:
                    failed_msgs.append(info)

        return {
            "exported": len(exported_files),
            "failed": len(failed_msgs),
            "dest_dir": str(dest_dir),
            "files": exported_files[:50],
            "errors": failed_msgs[:20],
        }

    registry.update(
        {
            "photos.query": photos_query,
            "photos.export": photos_export,
            "photos.detail": photo_detail,
            "photos.toggle_mark": photo_toggle_mark,
            "photos.set_date": photo_set_date,
            "photos.clear_date": photo_clear_date,
            "photos.similar": photos_similar,
            "photos.failed": photos_failed,
            "photos.decode": photo_decode,
            "dates.suspicious": dates_suspicious,
            "tags.list": tags_list,
            "saved_searches.list": saved_searches_list,
            "saved_searches.save": saved_searches_save,
            "saved_searches.delete": saved_searches_delete,
        }
    )
