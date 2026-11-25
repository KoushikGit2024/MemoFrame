"""View exports for MemoFrame GUI."""
from __future__ import annotations

from gui.views.gallery_view import GalleryView
from gui.views.people_view import PeopleView
from gui.views.duplicates_view import DuplicatesView
from gui.views.timeline_view import TimelineView
from gui.views.settings_view import SettingsView
from gui.views.detail_dialog import PhotoDetailDialog

__all__ = [
    "GalleryView",
    "PeopleView",
    "DuplicatesView",
    "TimelineView",
    "SettingsView",
    "PhotoDetailDialog",
]
