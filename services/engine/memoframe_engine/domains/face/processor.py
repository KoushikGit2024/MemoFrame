"""Per-image face outputs: anonymous labels, crops, annotated copy.

Labels ("Face 001") are positions within ONE image (left to right). They carry
no identity and say nothing about faces in other photographs.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from memoframe_engine.core.config import Settings
from memoframe_engine.domains.face.recognizer import FaceRecognizerSF
from memoframe_engine.domains.media.loader import ImageLoadError, load_image, load_image_bytes
from memoframe_engine.core.models import FaceBox
from memoframe_engine.domains.media.thumbnails import encode_jpeg, resize_to_fit, shard_dir
from memoframe_engine.utils.file_utils import atomic_write_bytes, output_name
from memoframe_engine.utils.logger import get_logger

log = get_logger("processing.face_processor")

ANNOTATED_MAX_SIDE = 1600
_BOX_COLOUR = (255, 64, 64)


def assign_labels(faces: list[FaceBox]) -> list[FaceBox]:
    """Number faces ``Face 001``, ``Face 002`` ... in the order given."""
    return [replace(f, label=f"Face {i:03d}") for i, f in enumerate(faces, start=1)]


def expand_box(face: FaceBox, img_w: int, img_h: int, margin: float) -> tuple[int, int, int, int]:
    """Crop rectangle ``(x0, y0, x1, y1)``: the box plus ``margin`` on each side, clipped."""
    mx, my = round(face.w * margin), round(face.h * margin)
    return (
        max(0, face.x - mx),
        max(0, face.y - my),
        min(img_w, face.x + face.w + mx),
        min(img_h, face.y + face.h + my),
    )


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def draw_annotations(pil: Image.Image, faces: list[FaceBox], scale: float) -> Image.Image:
    """Copy of ``pil`` with boxes and labels. ``scale`` = full-res / ``pil`` width."""
    out = pil.copy()
    draw = ImageDraw.Draw(out)
    line = max(2, round(max(out.size) / 400))
    font_size = max(12, line * 5)
    font = _font(font_size)
    for f in faces:
        x0, y0 = f.x / scale, f.y / scale
        x1, y1 = (f.x + f.w) / scale, (f.y + f.h) / scale
        draw.rectangle([x0, y0, x1, y1], outline=_BOX_COLOUR, width=line)
        text = f"{f.label or 'Face'} ({f.confidence:.2f})"
        ty = max(0.0, y0 - font_size - 4)
        left, top, right, bottom = draw.textbbox((x0, ty), text, font=font)
        draw.rectangle([left - 2, top - 2, right + 2, bottom + 2], fill=_BOX_COLOUR)
        draw.text((x0, ty), text, fill=(255, 255, 255), font=font)
    return out


def _to_decoded(face: FaceBox, scale: float) -> FaceBox:
    """Full-resolution face -> coordinates of an image decoded at 1/scale."""
    if scale == 1.0:
        return face
    lm = tuple(v / scale for v in face.landmarks) if face.landmarks else None
    return replace(
        face,
        x=round(face.x / scale),
        y=round(face.y / scale),
        w=round(face.w / scale),
        h=round(face.h / scale),
        landmarks=lm,
    )


def process_faces(
    image_id: int,
    source: Path,
    faces: list[FaceBox],
    settings: Settings,
    recognizer: FaceRecognizerSF | None = None,
    data: bytes | None = None,
) -> list[FaceBox]:
    """Label faces and write crops, annotated copy, and compute 128-d face embeddings.

    Returns the faces with ``label``, ``embedding`` (and ``crop_path`` when saved).
    Images without faces produce no files. Output problems are logged and never
    raised, so they cannot fail the image. The original file is only read.
    """
    labelled = assign_labels(faces)
    if not labelled:
        return labelled

    # If neither crops nor recognition are needed, return labelled
    if not (settings.save_face_crops or settings.save_annotated or recognizer is not None):
        return labelled

    max_side = None if settings.save_face_crops else 2400
    try:
        full = (
            load_image_bytes(data, source.name, max_side)
            if data is not None
            else load_image(source, max_side=max_side)
        )
    except ImageLoadError as exc:
        log.warning("Face outputs skipped (cannot reopen image): %s", exc)
        return labelled

    try:
        result: list[FaceBox] = []
        full_bgr = None
        if recognizer is not None:
            full_bgr = full.to_bgr()

        for i, face in enumerate(labelled, start=1):
            crop_path: str | None = None
            embedding: bytes | None = None

            if recognizer is not None and full_bgr is not None:
                embedding = recognizer.embed_face(full_bgr, _to_decoded(face, full.scale))

            if settings.save_face_crops:
                crop = full.pil.crop(
                    expand_box(face, full.width, full.height, settings.face_crop_margin)
                )
                crop = resize_to_fit(crop, settings.face_thumb_size)
                dest = shard_dir(settings.face_crops_dir, image_id) / output_name(
                    image_id, source, tag=f"f{i:03d}"
                )
                atomic_write_bytes(dest, encode_jpeg(crop, settings.jpeg_quality))
                crop_path = str(dest)

            result.append(replace(face, crop_path=crop_path, embedding=embedding))

        if settings.save_annotated:
            small = resize_to_fit(full.pil, ANNOTATED_MAX_SIDE)
            annotated = draw_annotations(small, result, full.width / small.width)
            dest = shard_dir(settings.annotated_dir, image_id) / output_name(image_id, source)
            atomic_write_bytes(dest, encode_jpeg(annotated, settings.jpeg_quality))
        return result
    except OSError as exc:
        log.warning("Could not write face outputs for %s: %s", source.name, exc)
        return labelled
