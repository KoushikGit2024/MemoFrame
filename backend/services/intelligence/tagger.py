"""Whole-image scene tagging with an ONNX classifier run through cv2.dnn.

The tagger receives ONE whole-image PIL picture. It never sees face boxes and
produces labels plus a whole-image vector, nothing face-specific.

Files (in ``<workspace>/models/tags/``):
  scene_model.onnx     ImageNet-style classifier (you provide it)
  scene_labels.txt     class names, one per line, in class order
  scene_tags.json      optional: {"input_size":224,"mean":[..],"std":[..],"output":"logits"|"probs"}
  tag_map.txt          optional: lines "class name => tag"; only mapped classes are kept and
                       classes mapped to the same tag add up
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from config import Settings
from utils.logger import get_logger

log = get_logger("core.tagger")

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
_SYNSET = re.compile(r"^n\d{8}\s+")


class TaggerUnavailableError(RuntimeError):
    """Tagging is enabled but the model or labels cannot be used."""


def clean_label(line: str) -> str:
    """``n01440764 tench, Thunnus thynnus`` -> ``tench``."""
    return _SYNSET.sub("", line.strip()).split(",")[0].strip()


def load_labels(path: Path) -> list[str]:
    labels = [clean_label(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not labels:
        raise TaggerUnavailableError(f"No labels found in {path}")
    return labels


def load_tag_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=>" in line and not line.lstrip().startswith("#"):
            source, tag = (part.strip() for part in line.split("=>", 1))
            if source and tag:
                mapping[source] = tag
    return mapping


class SceneTagger:
    """Turns a picture into tags and an embedding.

    ``forward`` takes a float32 NCHW blob and returns the model's 1-D output.
    """

    def __init__(
        self,
        forward: Callable[[np.ndarray], np.ndarray],
        labels: list[str],
        signature: str,
        *,
        top_k: int = 5,
        min_score: float = 0.15,
        size: int = 224,
        mean: tuple[float, ...] = IMAGENET_MEAN,
        std: tuple[float, ...] = IMAGENET_STD,
        output: str = "logits",
        tag_map: dict[str, str] | None = None,
    ) -> None:
        self._forward, self.labels, self.signature = forward, labels, signature
        self.top_k, self.min_score, self.size = top_k, min_score, size
        self._mean = np.array(mean, dtype=np.float32).reshape(1, 1, 3)
        self._std = np.array(std, dtype=np.float32).reshape(1, 1, 3)
        self.output = output
        self._groups: dict[str, np.ndarray] | None = None
        if tag_map:
            groups: dict[str, list[int]] = {}
            for i, label in enumerate(labels):
                if label in tag_map:
                    groups.setdefault(tag_map[label], []).append(i)
            self._groups = {t: np.array(ix) for t, ix in groups.items()}

    def _blob(self, pil: Image.Image) -> np.ndarray:
        short = round(self.size * 256 / 224)
        w, h = pil.size
        scale = short / min(w, h)
        resized = pil.convert("RGB").resize(
            (max(self.size, round(w * scale)), max(self.size, round(h * scale))),
            Image.Resampling.BILINEAR,
        )
        left, top = (resized.width - self.size) // 2, (resized.height - self.size) // 2
        arr = (
            np.asarray(
                resized.crop((left, top, left + self.size, top + self.size)), dtype=np.float32
            )
            / 255.0
        )
        return np.ascontiguousarray(((arr - self._mean) / self._std).transpose(2, 0, 1)[None])

    def probabilities(self, pil: Image.Image) -> np.ndarray:
        out = np.asarray(self._forward(self._blob(pil)), dtype=np.float64).reshape(-1)
        if out.size != len(self.labels):
            raise ValueError(
                f"Model outputs {out.size} values but the labels file has {len(self.labels)} lines."
            )
        if self.output == "logits":
            out = np.exp(out - out.max())
            out /= out.sum()
        return out

    def tag(self, pil: Image.Image) -> tuple[list[tuple[str, float]], bytes]:
        """``([(tag, score), ...], embedding_bytes)``. The embedding is sqrt(probabilities)
        as float16 (unit length), whole-image only."""
        probs = self.probabilities(pil)
        if self._groups is not None:
            scored = [(t, float(probs[ix].sum())) for t, ix in self._groups.items()]
            scored.sort(key=lambda p: -p[1])
        else:
            order = np.argsort(-probs, kind="stable")[: self.top_k]
            scored = [(self.labels[i], float(probs[i])) for i in order]
        tags = [(t, round(s, 4)) for t, s in scored if s >= self.min_score][: self.top_k]
        norm = float(np.sqrt(probs).dot(np.sqrt(probs))) ** 0.5 or 1.0
        return tags, (np.sqrt(probs) / norm).astype(np.float16).tobytes()


def _load_net(model: Path):
    try:
        data = np.frombuffer(model.read_bytes(), dtype=np.uint8)
        try:
            return cv2.dnn.readNetFromONNX(data)  # buffer form: works with non-ASCII paths
        except (cv2.error, TypeError):
            return cv2.dnn.readNetFromONNX(str(model))
    except (cv2.error, OSError) as exc:
        raise TaggerUnavailableError(f"Cannot load the tag model {model.name}: {exc}") from exc


def create_tagger(settings: Settings) -> SceneTagger | None:
    """Return a tagger, or ``None`` when tagging is switched off.

    Raises:
        TaggerUnavailableError: enabled, but files are missing or do not fit together.
    """
    if not settings.tagging_enabled:
        return None
    folder = settings.tag_dir
    model, labels_path = folder / settings.tag_model_file, folder / settings.tag_labels_file
    missing = [str(p) for p in (model, labels_path) if not p.is_file()]
    if missing:
        raise TaggerUnavailableError(
            "Tagging is enabled but these files are missing:\n  " + "\n  ".join(missing)
        )
    labels = load_labels(labels_path)
    config: dict = {}
    if (folder / "scene_tags.json").is_file():
        try:
            config = json.loads((folder / "scene_tags.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TaggerUnavailableError(f"scene_tags.json is invalid: {exc}") from exc
    map_path = folder / "tag_map.txt"
    tag_map = load_tag_map(map_path) if map_path.is_file() else None

    digest = hashlib.sha1()
    with model.open("rb") as fh:
        digest.update(fh.read(1_000_000))
    digest.update(str(model.stat().st_size).encode())
    digest.update(labels_path.read_bytes())
    if tag_map is not None:
        digest.update(map_path.read_bytes())
    digest.update(json.dumps(config, sort_keys=True).encode())

    net = _load_net(model)

    def forward(blob: np.ndarray) -> np.ndarray:
        net.setInput(blob)
        return net.forward()

    tagger = SceneTagger(
        forward,
        labels,
        digest.hexdigest()[:12],
        top_k=settings.tags_top_k,
        min_score=settings.tags_min_score,
        size=int(config.get("input_size", 224)),
        mean=tuple(config.get("mean", IMAGENET_MEAN)),
        std=tuple(config.get("std", IMAGENET_STD)),
        output=config.get("output", "logits"),
        tag_map=tag_map,
    )
    try:
        tagger.probabilities(Image.new("RGB", (64, 64)))  # fail early on a mismatched pair
    except (cv2.error, ValueError) as exc:
        raise TaggerUnavailableError(f"Tag model check failed: {exc}") from exc
    return tagger
