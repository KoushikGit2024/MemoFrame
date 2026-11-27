"""Person and face management mixin for the Engine public interface."""

from __future__ import annotations

from typing import Any

from engine.errors import EngineError, ErrorCode


class PersonEngineMixin:
    """Methods for managing people, face assignments, and face identification."""

    def _people_changed(self) -> None:
        from services.pipeline import orchestrator as pipeline

        pipeline.update_search_index(self.settings, self.db)  # names in the text index

    def get_persons(self) -> list[dict[str, Any]]:
        """List all identified person clusters with names, cover faces, and counts."""
        from engine.api import _row, _translated

        @_translated
        def _impl():
            return [_row(r) for r in self.db.list_persons()]

        return _impl()

    def get_person(self, person_id: int) -> dict[str, Any] | None:
        """Get details for a single person cluster."""
        from engine.api import _row, _translated

        @_translated
        def _impl():
            row = self.db.get_person(person_id)
            return _row(row) if row else None

        return _impl()

    def rename_person(self, person_id: int, new_name: str, confirm_faces: bool = False) -> bool:
        """Name a person."""
        from engine.api import _translated
        from services.pipeline import orchestrator as pipeline

        @_translated
        def _impl():
            clean = (new_name or "").strip()
            if not clean:
                raise EngineError(ErrorCode.INVALID_INPUT, "Person name cannot be empty.")
            if self.db.get_person(person_id) is None:
                raise EngineError(ErrorCode.INVALID_INPUT, f"No person with id {person_id}.")
            ok = self.db.rename_person(person_id, clean)
            if ok:
                if confirm_faces:
                    self.db.confirm_person(person_id)
                pipeline.update_search_index(self.settings, self.db)
            return ok

        return _impl()

    def get_person_faces(
        self, person_id: int, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Faces of one person, best first."""
        from engine.api import _row, _translated

        @_translated
        def _impl():
            return [_row(r) for r in self.db.person_faces(person_id, limit, offset)]

        return _impl()

    def get_unassigned_faces(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        from engine.api import _row, _translated

        @_translated
        def _impl():
            return [_row(r) for r in self.db.unassigned_faces(limit, offset)]

        return _impl()

    def assign_face(self, face_id: int, person_id: int | None) -> None:
        """Move a face to a person, or pass None to remove it from all people."""
        from engine.api import _translated

        @_translated
        def _impl():
            self.db.assign_face(face_id, person_id)
            self._people_changed()

        return _impl()

    def create_person(self, name: str, face_ids: list[int]) -> int:
        """Make a new named person from specific faces. Returns the new person id."""
        from engine.api import _translated

        @_translated
        def _impl():
            pid = self.db.create_person(name, face_ids)
            self._people_changed()
            return pid

        return _impl()

    def merge_persons(self, keep_id: int, merge_id: int) -> dict[str, Any] | None:
        """Merge two clusters of the same person."""
        from engine.api import _translated

        @_translated
        def _impl():
            self.db.merge_persons(keep_id, merge_id)
            self._people_changed()
            return self.get_person(keep_id)

        return _impl()

    def confirm_person(self, person_id: int) -> int:
        """Mark a cluster as correct: its faces are locked."""
        from engine.api import _translated

        @_translated
        def _impl():
            return self.db.confirm_person(person_id)

        return _impl()

    def unlock_face(self, face_id: int) -> bool:
        """Let automatic clustering decide this face again."""
        from engine.api import _translated

        @_translated
        def _impl():
            return self.db.unlock_face(face_id)

        return _impl()

    def discard_face(self, face_id: int) -> bool:
        """Mark a detected face as not-a-face (ignored) and update counts."""
        from engine.api import _translated

        @_translated
        def _impl():
            ok = self.db.discard_face(face_id)
            if ok:
                self._people_changed()
            return ok

        return _impl()

    def set_person_cover(self, person_id: int, face_id: int) -> bool:
        """Set a person's default (cover) face."""
        from engine.api import _translated

        @_translated
        def _impl():
            return self.db.set_person_cover(person_id, face_id)

        return _impl()

    def name_face(self, face_id: int, name: str) -> int:
        """Name a single face."""
        from engine.api import _translated

        @_translated
        def _impl():
            clean = (name or "").strip()
            if not clean:
                raise EngineError(ErrorCode.INVALID_INPUT, "Person name cannot be empty.")
            existing = [p for p in self.get_persons() if p.get("name", "").lower() == clean.lower()]
            if existing:
                pid = int(existing[0]["id"])
                self.db.assign_face(face_id, pid)
            else:
                pid = self.db.create_person(clean, [face_id])
            self.db.set_face_locked(face_id, True)
            self._people_changed()
            return pid

        return _impl()
