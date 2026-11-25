r"""Rules for displaying face box names and labels.

Rule:
A box shows a name only when:
  1. `locked == 1` (user confirmed/named/assigned the face)
  2. It belongs to a person (`person_id is not None`)
  3. The person's name is not the default `Person NN` (regex `r"^Person \d+$"`).

Everything else gets a dashed, unlabeled box with a "click to name it" tooltip.
Internal `Face 001` labels stay in the database and are never displayed.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

_DEFAULT_PERSON_RE = re.compile(r"^Person \d+$", re.IGNORECASE)


def face_display_name(face: Mapping[str, Any]) -> str | None:
    """Return the name to render on the face box, or None if it should be unlabeled."""
    # 1. Must be locked
    locked = face.get("locked")
    if not locked:
        return None

    # 2. Must belong to a person
    if face.get("person_id") is None:
        return None

    # 3. Person name must exist and not match Person NN
    name = (face.get("person_name") or "").strip()
    if not name or _DEFAULT_PERSON_RE.match(name):
        return None

    return name
