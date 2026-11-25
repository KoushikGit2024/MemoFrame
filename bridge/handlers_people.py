"""RPC handlers for people management, face review, naming, assignment, and merging."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any


def register_people_handlers(registry: dict[str, Any], ctx: Any) -> None:
    """Register people and face management RPC handlers."""

    def persons_list(_params: dict[str, Any]) -> list[dict[str, Any]]:
        eng = ctx.require_engine()
        with ctx.lock:
            return list(eng.get_persons() or [])

    def persons_get(params: dict[str, Any]) -> dict[str, Any] | None:
        eng = ctx.require_engine()
        with ctx.lock:
            row = eng.get_person(int(params["person_id"]))
            return dict(row) if row else None

    def persons_rename(params: dict[str, Any]) -> dict[str, Any]:
        person_id = int(params["person_id"])
        new_name = str(params["new_name"]).strip()
        confirm = bool(params.get("confirm", True))
        eng = ctx.require_engine()
        with ctx.lock:
            eng.rename_person(person_id, new_name, confirm)
        return {"person_id": person_id, "name": new_name}

    def persons_merge(params: dict[str, Any]) -> dict[str, Any]:
        keep_id = int(params["keep_id"])
        other_ids = [int(pid) for pid in (params.get("other_ids") or []) if int(pid) != keep_id]
        eng = ctx.require_engine()
        with ctx.lock:
            for pid in other_ids:
                eng.merge_persons(keep_id, pid)
        return {"keep_id": keep_id, "merged": other_ids}

    def persons_confirm(params: dict[str, Any]) -> dict[str, Any]:
        person_id = int(params["person_id"])
        eng = ctx.require_engine()
        with ctx.lock:
            count = eng.confirm_person(person_id)
        return {"person_id": person_id, "confirmed": int(count or 0)}

    def faces_for_person(params: dict[str, Any]) -> list[dict[str, Any]]:
        person_id = params.get("person_id")
        limit = max(1, min(200, int(params.get("limit") or 60)))
        offset = max(0, int(params.get("offset") or 0))
        eng = ctx.require_engine()
        with ctx.lock:
            if person_id is None:
                return list(eng.get_unassigned_faces(limit, offset) or [])
            return list(eng.get_person_faces(int(person_id), limit, offset) or [])

    def faces_name(params: dict[str, Any]) -> dict[str, Any]:
        face_id = int(params["face_id"])
        name = str(params["name"]).strip()
        eng = ctx.require_engine()
        with ctx.lock:
            eng.name_face(face_id, name)
        return {"face_id": face_id, "name": name}

    def faces_assign(params: dict[str, Any]) -> dict[str, Any]:
        face_id = int(params["face_id"])
        raw_pid = params.get("person_id")
        person_id = int(raw_pid) if raw_pid is not None else None
        eng = ctx.require_engine()
        with ctx.lock:
            eng.assign_face(face_id, person_id)
        return {"face_id": face_id, "person_id": person_id}

    def faces_crop(params: dict[str, Any]) -> dict[str, Any]:
        """Crop a face bounding box from disk via Pillow and return as JPEG data URL."""
        path = Path(str(params.get("path", "")))
        if not path.is_file():
            return {"data_url": None}
        x, y, w, h = int(params["x"]), int(params["y"]), int(params["w"]), int(params["h"])
        size = max(48, min(256, int(params.get("size") or 96)))
        try:
            import services.vision.loader  # noqa: F401
        except Exception:
            pass
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            pad = int(max(w, h) * 0.2)
            left = max(0, x - pad)
            top = max(0, y - pad)
            right = min(im.width, x + w + pad)
            bottom = min(im.height, y + h + pad)
            if right <= left or bottom <= top:
                return {"data_url": None}
            crop = im.crop((left, top, right, bottom))
            crop.thumbnail((size, size), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return {"data_url": f"data:image/jpeg;base64,{b64}"}

    registry.update({
        "persons.list": persons_list,
        "persons.get": persons_get,
        "persons.rename": persons_rename,
        "persons.merge": persons_merge,
        "persons.confirm": persons_confirm,
        "faces.list": faces_for_person,
        "faces.name": faces_name,
        "faces.assign": faces_assign,
        "faces.crop": faces_crop,
    })
