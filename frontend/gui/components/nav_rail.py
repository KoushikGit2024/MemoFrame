"""Left sidebar navigation rail with crisp icons, active states, and sleek Theme Toggler."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.theme_manager import THEMES


class NavButton(QPushButton):
    """Custom navigation item with icon glyph and label."""

    def __init__(self, key: str, icon_str: str, label_str: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.icon_str = icon_str
        self.label_str = label_str
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setProperty("class", "NavButton")
        display = f"{icon_str}   {label_str}" if icon_str else label_str
        self.setText(display)


class _ThemeSwatchButton(QPushButton):
    """Compact circular theme color swatch button with active indicator ring."""

    def __init__(self, theme_name: str, accent_hex: str, bg_hex: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme_name = theme_name
        self._accent = accent_hex
        self._bg = bg_hex
        self.setCheckable(True)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Switch to {theme_name}")
        self._update_style(False)

    def set_selected(self, selected: bool) -> None:
        self.setChecked(selected)
        self._update_style(selected)

    def _update_style(self, selected: bool) -> None:
        border = f"2px solid {self._accent}" if selected else "2px solid rgba(140, 150, 165, 0.35)"
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {self._accent if selected else self._bg};"
            f"  border: {border};"
            f"  border-radius: 11px;"
            f"  padding: 0px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  border: 2px solid {self._accent};"
            f"  background-color: {self._accent};"
            f"}}"
        )


class NavigationRail(QFrame):
    """Modern web-inspired sidebar rail with view navigation and integrated theme toggler."""

    tab_selected = pyqtSignal(str)
    theme_selected = pyqtSignal(str)
    light_dark_toggled = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setProperty("class", "NavRail")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(6)

        # Brand Lockup
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 0, 8, 2)
        brand_row.setSpacing(9)

        accent_dot = QLabel()
        accent_dot.setFixedSize(10, 10)
        accent_dot.setProperty("class", "BrandAccentDot")
        brand_row.addWidget(accent_dot)

        brand_lbl = QLabel("MEMOFRAME")
        brand_lbl.setProperty("class", "BrandTitle")
        brand_row.addWidget(brand_lbl)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        subtitle = QLabel("Photo & Face Studio")
        subtitle.setProperty("class", "BrandSubtitle")
        subtitle.setContentsMargins(27, 0, 0, 14)
        layout.addWidget(subtitle)

        # Primary Workspace Navigation
        nav_section = QLabel("WORKSPACE")
        nav_section.setProperty("class", "NavSectionLabel")
        layout.addWidget(nav_section)
        layout.addSpacing(2)

        self.buttons: dict[str, NavButton] = {}
        tabs = [
            ("photos", "◫", "Photos"),
            ("people", "◎", "People"),
            ("duplicates", "⧉", "Duplicates"),
            ("timeline", "◷", "Timeline"),
            ("settings", "⚙", "Settings"),
        ]

        for key, icon, name in tabs:
            btn = NavButton(key, icon, name)
            btn.clicked.connect(lambda checked, k=key: self._on_tab_clicked(k))
            self.buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Subtle Divider above Theme Switcher
        divider = QFrame()
        divider.setProperty("class", "NavDivider")
        layout.addWidget(divider)
        layout.addSpacing(6)

        # Integrated Theme Toggler Card
        theme_box = QFrame()
        theme_box.setProperty("class", "ThemeTogglerBox")
        tb_layout = QVBoxLayout(theme_box)
        tb_layout.setContentsMargins(10, 10, 10, 10)
        tb_layout.setSpacing(8)

        theme_hdr = QHBoxLayout()
        theme_hdr.setContentsMargins(2, 0, 2, 0)
        t_lbl = QLabel("THEME")
        t_lbl.setProperty("class", "NavSectionLabel")
        t_lbl.setStyleSheet("padding-left: 0px;")
        theme_hdr.addWidget(t_lbl)
        theme_hdr.addStretch()

        self.active_theme_lbl = QLabel("Dark Slate")
        self.active_theme_lbl.setProperty("class", "Dim")
        theme_hdr.addWidget(self.active_theme_lbl)
        tb_layout.addLayout(theme_hdr)

        # Quick Light / Dark Toggle Button
        self.btn_mode_toggle = QPushButton("☀  Light Mode")
        self.btn_mode_toggle.setProperty("class", "ThemeModeToggle")
        self.btn_mode_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_toggle.setToolTip("Quickly toggle between Dark and Light mode")
        self.btn_mode_toggle.clicked.connect(self.light_dark_toggled.emit)
        tb_layout.addWidget(self.btn_mode_toggle)

        # 5-Palette Color Swatch Row
        swatch_row = QHBoxLayout()
        swatch_row.setContentsMargins(2, 2, 2, 0)
        swatch_row.setSpacing(8)
        swatch_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.theme_swatches: dict[str, _ThemeSwatchButton] = {}
        for name, palette in THEMES.items():
            swatch = _ThemeSwatchButton(name, palette.accent, palette.bg_card if palette.is_dark else "#e2e8f0")
            swatch.clicked.connect(lambda checked, t_name=name: self.theme_selected.emit(t_name))
            self.theme_swatches[name] = swatch
            swatch_row.addWidget(swatch)

        tb_layout.addLayout(swatch_row)
        layout.addWidget(theme_box)

        # Set default active tab and theme
        self.set_active("photos")
        self.set_theme("Dark Slate")

    def _on_tab_clicked(self, key: str) -> None:
        self.set_active(key)
        self.tab_selected.emit(key)

    def set_active(self, key: str) -> None:
        for k, btn in self.buttons.items():
            btn.setChecked(k == key)

    def set_theme(self, theme_name: str) -> None:
        """Synchronize the sidebar theme toggler UI with the active palette."""
        if theme_name not in THEMES:
            return
        palette = THEMES[theme_name]
        self.active_theme_lbl.setText(theme_name.split()[0])
        self.btn_mode_toggle.setText("☾  Dark Mode" if not palette.is_dark else "☀  Light Mode")
        for name, btn in self.theme_swatches.items():
            btn.set_selected(name == theme_name)
