"""Search, timeline, saved searches, tags, and similarity mixin for Engine."""

from __future__ import annotations

from typing import Any

from engine.errors import EngineError, ErrorCode


class SearchEngineMixin:
    """Search, discovery, and query methods for Engine."""

    def find(
        self, *, sort: str = "date", limit: int = 100, offset: int = 0, **filters: Any
    ) -> list[dict[str, Any]]:
        from engine.api import _row, _translated
        from services.pipeline import orchestrator as pipeline

        @_translated
        def _impl():
            if filters.get("text"):
                pipeline.update_search_index(self.settings, self.db)
            return [
                _row(r)
                for r in self.db.find_images(sort=sort, limit=limit, offset=offset, **filters)
            ]

        return _impl()

    def count(self, **filters: Any) -> int:
        from engine.api import _translated
        from services.pipeline import orchestrator as pipeline

        @_translated
        def _impl():
            if filters.get("text"):
                pipeline.update_search_index(self.settings, self.db)
            return self.db.count_images(**filters)

        return _impl()

    def timeline(self, granularity: str = "month") -> list[dict[str, Any]]:
        from engine.api import _translated

        @_translated
        def _impl():
            return self.db.timeline(granularity)

        return _impl()

    def save_search(self, name: str, filters: dict[str, Any]) -> None:
        from engine.api import _translated

        @_translated
        def _impl():
            self.db.save_search(name, filters)

        return _impl()

    def list_saved_searches(self) -> list[dict[str, Any]]:
        from engine.api import _translated

        @_translated
        def _impl():
            return self.db.list_saved_searches()

        return _impl()

    def delete_saved_search(self, name: str) -> bool:
        from engine.api import _translated

        @_translated
        def _impl():
            return self.db.delete_saved_search(name)

        return _impl()

    def run_saved_search(
        self, name: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        from engine.api import _translated

        @_translated
        def _impl():
            saved = self.db.get_saved_search(name)
            if saved is None:
                raise EngineError(ErrorCode.INVALID_INPUT, f"No saved search named {name!r}.")
            return self.find(limit=limit, offset=offset, **saved)

        return _impl()

    def moves(self) -> list[dict[str, Any]]:
        from engine.api import _row, _translated
        from services.pipeline import maintenance

        @_translated
        def _impl():
            maintenance.refresh_states(self.db)
            self.db.restore_marks()
            return [_row(r) for r in self.db.find_moves()]

        return _impl()

    def get_tags(self, image_id: int) -> list[dict[str, Any]]:
        from engine.api import _row, _translated

        @_translated
        def _impl():
            return [_row(r) for r in self.db.get_tags(image_id)]

        return _impl()

    def list_tags(self, limit: int = 100) -> list[dict[str, Any]]:
        from engine.api import _translated

        @_translated
        def _impl():
            return [
                {"label": r["label"], "count": int(r["n"])} for r in self.db.list_tag_counts(limit)
            ]

        return _impl()

    def similar(self, image_id: int, limit: int = 20) -> list[dict[str, Any]]:
        from engine.api import _row, _translated
        from services.intelligence.similar import find_similar

        @_translated
        def _impl():
            out = []
            for other_id, score in find_similar(self.db, image_id, limit):
                row = self.db.get_image(other_id)
                if row is not None:
                    out.append({**_row(row), "similarity": round(score, 4)})
            return out

        return _impl()
