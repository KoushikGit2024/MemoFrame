"""Theme Manager for MemoFrame Desktop GUI.

Provides multi-colored, dynamically switchable modern themes with complete
coverage across every view, card, table, scrollbar, dialog, and control:
- Dark Slate (Default - Modern Obsidian Charcoal with Electric Blue)
- Midnight Purple (Deep Cosmic Indigo with Luminous Violet)
- Emerald Forest (Deep Botanical Pine with Crisp Jade)
- Cyber Amber (Matte Carbon with Warm Amber Gold)
- Light Canvas (Porcelain Daylight Surface with Crisp Cobalt)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    name: str
    bg_app: str
    bg_card: str
    bg_input: str
    border: str
    text_primary: str
    text_secondary: str
    accent: str
    accent_hover: str
    accent_light: str
    danger: str
    success: str
    box_overlay: str
    bg_sidebar: str = "#0d1014"
    bg_elevated: str = "#22272f"
    border_subtle: str = "#21262e"
    badge_bg: str = "#21262d"
    accent_text: str = "#ffffff"
    danger_bg: str = "rgba(244, 63, 94, 0.14)"
    success_bg: str = "rgba(16, 185, 129, 0.14)"
    is_dark: bool = True


THEMES: dict[str, ThemePalette] = {
    "Dark Slate": ThemePalette(
        name="Dark Slate",
        bg_app="#0f1216",
        bg_sidebar="#0b0e12",
        bg_card="#161b22",
        bg_elevated="#1f252e",
        bg_input="#0d1117",
        border="#2b333f",
        border_subtle="#212730",
        text_primary="#edf2f7",
        text_secondary="#8b95a5",
        accent="#2f81f7",
        accent_hover="#58a6ff",
        accent_light="rgba(47, 129, 247, 0.16)",
        accent_text="#ffffff",
        danger="#f85149",
        success="#3fb950",
        badge_bg="#21262d",
        box_overlay="rgba(88, 166, 255, 0.22)",
        danger_bg="rgba(248, 81, 73, 0.15)",
        success_bg="rgba(63, 185, 80, 0.15)",
        is_dark=True,
    ),
    "Midnight Purple": ThemePalette(
        name="Midnight Purple",
        bg_app="#0e0d16",
        bg_sidebar="#0a0911",
        bg_card="#171525",
        bg_elevated="#211e34",
        bg_input="#110f1d",
        border="#322c4a",
        border_subtle="#241f38",
        text_primary="#f7f6ff",
        text_secondary="#a09db8",
        accent="#8b5cf6",
        accent_hover="#a78bfa",
        accent_light="rgba(139, 92, 246, 0.18)",
        accent_text="#ffffff",
        danger="#fb7185",
        success="#34d399",
        badge_bg="#24203a",
        box_overlay="rgba(167, 139, 250, 0.24)",
        danger_bg="rgba(251, 113, 133, 0.16)",
        success_bg="rgba(52, 211, 153, 0.15)",
        is_dark=True,
    ),
    "Emerald Forest": ThemePalette(
        name="Emerald Forest",
        bg_app="#0b130f",
        bg_sidebar="#080e0b",
        bg_card="#121e18",
        bg_elevated="#1a2b22",
        bg_input="#0a110d",
        border="#243a2e",
        border_subtle="#1a2c22",
        text_primary="#ecf6f0",
        text_secondary="#8ca89a",
        accent="#10b981",
        accent_hover="#34d399",
        accent_light="rgba(16, 185, 129, 0.16)",
        accent_text="#ffffff",
        danger="#f87171",
        success="#34d399",
        badge_bg="#182b21",
        box_overlay="rgba(16, 185, 129, 0.24)",
        danger_bg="rgba(248, 113, 113, 0.15)",
        success_bg="rgba(52, 211, 153, 0.16)",
        is_dark=True,
    ),
    "Cyber Amber": ThemePalette(
        name="Cyber Amber",
        bg_app="#121212",
        bg_sidebar="#0c0c0c",
        bg_card="#1b1b1b",
        bg_elevated="#262626",
        bg_input="#101010",
        border="#343434",
        border_subtle="#262626",
        text_primary="#f5f5f4",
        text_secondary="#a1a1aa",
        accent="#f59e0b",
        accent_hover="#fbbf24",
        accent_light="rgba(245, 158, 11, 0.16)",
        accent_text="#111111",
        danger="#f87171",
        success="#34d399",
        badge_bg="#27241d",
        box_overlay="rgba(245, 158, 11, 0.24)",
        danger_bg="rgba(248, 113, 113, 0.15)",
        success_bg="rgba(52, 211, 153, 0.15)",
        is_dark=True,
    ),
    "Light Canvas": ThemePalette(
        name="Light Canvas",
        bg_app="#f4f6f9",
        bg_sidebar="#ffffff",
        bg_card="#ffffff",
        bg_elevated="#eef2f6",
        bg_input="#f8fafc",
        border="#d8dee6",
        border_subtle="#e6ebf1",
        text_primary="#111827",
        text_secondary="#5f6b7a",
        accent="#0969da",
        accent_hover="#218bff",
        accent_light="rgba(9, 105, 218, 0.10)",
        accent_text="#ffffff",
        danger="#cf222e",
        success="#1a7f37",
        badge_bg="#edf1f5",
        box_overlay="rgba(9, 105, 218, 0.22)",
        danger_bg="rgba(207, 34, 46, 0.10)",
        success_bg="rgba(26, 127, 55, 0.10)",
        is_dark=False,
    ),
}

_ACTIVE_THEME: ThemePalette = THEMES["Dark Slate"]


def set_active_theme(theme_name: str) -> ThemePalette:
    """Update the active global palette reference for custom-painted widgets."""
    global _ACTIVE_THEME
    if theme_name in THEMES:
        _ACTIVE_THEME = THEMES[theme_name]
    return _ACTIVE_THEME


def get_active_theme() -> ThemePalette:
    """Return the currently active ThemePalette."""
    return _ACTIVE_THEME


def build_stylesheet(theme: ThemePalette) -> str:
    """Generate a modern, web-inspired Qt stylesheet covering all views and controls."""
    return f"""
    /* === Base Window & Surfaces === */
    QMainWindow, QDialog {{
        background-color: {theme.bg_app};
        color: {theme.text_primary};
        font-family: "Segoe UI", "Inter", -apple-system, Roboto, sans-serif;
    }}

    QWidget {{
        color: {theme.text_primary};
        font-family: "Segoe UI", "Inter", -apple-system, Roboto, sans-serif;
    }}

    QWidget#CentralWidget, QWidget#TransparentContainer, QStackedWidget {{
        background-color: {theme.bg_app};
    }}

    QWidget#ScrollContainer {{
        background-color: transparent;
    }}

    /* === Navigation Sidebar === */
    QFrame[class="NavRail"] {{
        background-color: {theme.bg_sidebar};
        border: none;
        border-right: 1px solid {theme.border_subtle};
    }}

    QLabel[class="BrandTitle"] {{
        font-size: 14px;
        font-weight: 800;
        letter-spacing: 1.6px;
        color: {theme.text_primary};
        background: transparent;
    }}

    QLabel[class="BrandAccentDot"] {{
        background-color: {theme.accent};
        border-radius: 5px;
    }}

    QLabel[class="BrandSubtitle"] {{
        font-size: 11px;
        font-weight: 500;
        color: {theme.text_secondary};
        background: transparent;
    }}

    QLabel[class="NavSectionLabel"] {{
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.1px;
        color: {theme.text_secondary};
        padding-left: 10px;
        background: transparent;
    }}

    QPushButton[class="NavButton"] {{
        text-align: left;
        padding: 0px 14px;
        border-radius: 9px;
        font-size: 13px;
        font-weight: 600;
        background-color: transparent;
        color: {theme.text_secondary};
        border: 1px solid transparent;
    }}

    QPushButton[class="NavButton"]:hover {{
        background-color: {theme.bg_elevated};
        color: {theme.text_primary};
    }}

    QPushButton[class="NavButton"]:checked {{
        background-color: {theme.accent_light};
        color: {theme.accent_hover if theme.is_dark else theme.accent};
        border: 1px solid {theme.accent};
    }}

    QFrame[class="NavDivider"] {{
        background-color: {theme.border_subtle};
        border: none;
        max-height: 1px;
        min-height: 1px;
    }}

    QFrame[class="ThemeTogglerBox"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
    }}

    QPushButton[class="ThemeModeToggle"] {{
        background-color: {theme.bg_elevated};
        color: {theme.text_primary};
        border: 1px solid {theme.border};
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 11px;
        font-weight: 600;
        text-align: center;
    }}

    QPushButton[class="ThemeModeToggle"]:hover {{
        border-color: {theme.accent};
        background-color: {theme.accent_light};
        color: {theme.accent_hover if theme.is_dark else theme.accent};
    }}

    /* === Cards & Panels === */
    QFrame[class="Card"], QFrame.Card {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
    }}

    QFrame[class="PhotoCard"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
    }}

    QFrame[class="PhotoCard"]:hover {{
        border: 1px solid {theme.accent};
        background-color: {theme.bg_elevated};
    }}

    QFrame[class="ToolbarCard"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
    }}

    QFrame[class="PersonRowCard"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
    }}

    QFrame[class="PersonRowCard"]:hover {{
        border-color: {theme.accent};
    }}

    QFrame[class="EventCard"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 14px;
    }}

    QFrame[class="StatTile"] {{
        background-color: {theme.bg_input};
        border: 1px solid {theme.border_subtle};
        border-radius: 10px;
    }}

    QFrame[class="InspectorDrawer"] {{
        background-color: {theme.bg_card};
        border: none;
        border-left: 1px solid {theme.border_subtle};
    }}

    QFrame[class="CanvasToolbar"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 10px;
    }}

    QFrame[class="FooterBar"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 10px;
    }}

    QFrame[class="EmptyStateCard"] {{
        background-color: {theme.bg_card};
        border: 1px dashed {theme.border};
        border-radius: 14px;
    }}

    QFrame[class="KeeperCard"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.success};
        border-radius: 14px;
    }}

    QFrame[class="DuplicateCard"] {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 14px;
    }}

    QFrame[class="ThemeOptionCard"] {{
        background-color: {theme.bg_input};
        border: 1px solid {theme.border_subtle};
        border-radius: 10px;
    }}

    QFrame[class="ThemeOptionCard"]:hover {{
        border-color: {theme.accent};
    }}

    QFrame[class="ThemeOptionCardSelected"] {{
        background-color: {theme.accent_light};
        border: 2px solid {theme.accent};
        border-radius: 10px;
    }}

    /* === Typography === */
    QLabel {{
        color: {theme.text_primary};
        background: transparent;
    }}

    QLabel[class="PageTitle"] {{
        font-size: 20px;
        font-weight: 700;
        color: {theme.text_primary};
    }}

    QLabel[class="PageSubtitle"] {{
        font-size: 12px;
        color: {theme.text_secondary};
    }}

    QLabel[class="SectionTitle"] {{
        font-size: 14px;
        font-weight: 700;
        color: {theme.text_primary};
    }}

    QLabel[class="AccentTitle"] {{
        font-size: 14px;
        font-weight: 700;
        color: {theme.accent_hover if theme.is_dark else theme.accent};
    }}

    QLabel[class="CardTitle"] {{
        font-size: 12px;
        font-weight: 600;
        color: {theme.text_primary};
    }}

    QLabel[class="StatValue"] {{
        font-size: 22px;
        font-weight: 700;
        color: {theme.accent_hover if theme.is_dark else theme.accent};
    }}

    QLabel[class="StatLabel"] {{
        font-size: 11px;
        font-weight: 600;
        color: {theme.text_secondary};
    }}

    QLabel[class="Dim"], QLabel.Dim {{
        color: {theme.text_secondary};
        font-size: 11px;
    }}

    QLabel[class="Heading"], QLabel.Heading {{
        font-size: 15px;
        font-weight: 700;
        color: {theme.text_primary};
    }}

    QLabel[class="MetaKey"] {{
        font-size: 11px;
        font-weight: 600;
        color: {theme.text_secondary};
    }}

    QLabel[class="MetaValue"] {{
        font-size: 12px;
        font-weight: 500;
        color: {theme.text_primary};
    }}

    QLabel[class="FaceBadge"] {{
        background-color: {theme.badge_bg};
        color: {theme.text_secondary};
        border: 1px solid {theme.border_subtle};
        border-radius: 6px;
        padding: 1px 6px;
        font-size: 10px;
        font-weight: 600;
    }}

    QLabel[class="CountChip"] {{
        background-color: {theme.accent_light};
        color: {theme.accent_hover if theme.is_dark else theme.accent};
        border-radius: 10px;
        padding: 2px 9px;
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel[class="DateChip"] {{
        background-color: {theme.badge_bg};
        color: {theme.text_secondary};
        border-radius: 8px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }}

    QLabel[class="KeeperBadge"] {{
        background-color: {theme.success_bg};
        color: {theme.success};
        border: 1px solid {theme.success};
        border-radius: 8px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel[class="DuplicateBadge"] {{
        background-color: {theme.danger_bg};
        color: {theme.danger};
        border: 1px solid {theme.danger};
        border-radius: 8px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
    }}

    QLabel[class="StatusHealthy"] {{
        color: {theme.success};
        font-size: 12px;
        font-weight: 600;
    }}

    QLabel[class="StatusIssue"] {{
        color: {theme.danger};
        font-size: 12px;
        font-weight: 600;
    }}

    QLabel[class="ThumbCanvas"] {{
        background-color: {theme.bg_input};
        border-radius: 8px;
        color: {theme.text_secondary};
        font-size: 11px;
    }}

    /* === Inputs & Selectors === */
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {theme.bg_input};
        border: 1px solid {theme.border};
        border-radius: 8px;
        padding: 6px 10px;
        color: {theme.text_primary};
        font-size: 12px;
        min-height: 20px;
    }}

    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
        border-color: {theme.accent};
    }}

    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {theme.accent};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {theme.bg_card};
        color: {theme.text_primary};
        border: 1px solid {theme.border};
        border-radius: 8px;
        selection-background-color: {theme.accent_light};
        selection-color: {theme.text_primary};
        padding: 4px;
        outline: 0;
    }}

    QSpinBox::up-button, QSpinBox::down-button {{
        width: 18px;
        border: none;
        background: transparent;
    }}

    /* === Buttons & Segmented Controls === */
    QPushButton {{
        background-color: {theme.accent};
        color: {theme.accent_text};
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 7px 14px;
        font-weight: 600;
        font-size: 12px;
    }}

    QPushButton:hover {{
        background-color: {theme.accent_hover};
    }}

    QPushButton:disabled {{
        background-color: {theme.bg_elevated};
        color: {theme.text_secondary};
        border-color: {theme.border_subtle};
    }}

    QPushButton[class="Secondary"], QPushButton.Secondary {{
        background-color: {theme.bg_elevated};
        border: 1px solid {theme.border};
        color: {theme.text_primary};
    }}

    QPushButton[class="Secondary"]:hover, QPushButton.Secondary:hover {{
        border-color: {theme.accent};
        background-color: {theme.accent_light};
        color: {theme.accent_hover if theme.is_dark else theme.accent};
    }}

    QPushButton[class="Ghost"] {{
        background-color: transparent;
        border: 1px solid transparent;
        color: {theme.text_secondary};
        padding: 5px 10px;
    }}

    QPushButton[class="Ghost"]:hover {{
        background-color: {theme.bg_elevated};
        color: {theme.text_primary};
    }}

    QPushButton[class="Danger"], QPushButton.Danger {{
        background-color: {theme.danger};
        color: #ffffff;
    }}

    QFrame[class="SegmentedControl"] {{
        background-color: {theme.bg_input};
        border: 1px solid {theme.border};
        border-radius: 9px;
    }}

    QPushButton[class="SegmentButton"] {{
        background-color: transparent;
        color: {theme.text_secondary};
        border: none;
        border-radius: 7px;
        padding: 5px 12px;
        font-size: 12px;
        font-weight: 600;
    }}

    QPushButton[class="SegmentButton"]:hover {{
        color: {theme.text_primary};
        background-color: {theme.bg_elevated};
    }}

    QPushButton[class="SegmentButton"]:checked {{
        background-color: {theme.accent};
        color: {theme.accent_text};
    }}

    /* === Tables & Lists === */
    QTableWidget {{
        background-color: {theme.bg_card};
        alternate-background-color: {theme.bg_input};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
        gridline-color: transparent;
        font-size: 12px;
        color: {theme.text_primary};
        outline: 0;
    }}

    QTableWidget::item {{
        padding: 6px 10px;
        border-bottom: 1px solid {theme.border_subtle};
    }}

    QTableWidget::item:hover {{
        background-color: {theme.bg_elevated};
    }}

    QTableWidget::item:selected {{
        background-color: {theme.accent_light};
        color: {theme.text_primary};
    }}

    QHeaderView::section {{
        background-color: {theme.bg_elevated};
        color: {theme.text_secondary};
        padding: 8px 10px;
        font-size: 11px;
        font-weight: 700;
        border: none;
        border-bottom: 1px solid {theme.border};
    }}

    QTableCornerButton::section {{
        background-color: {theme.bg_elevated};
        border: none;
    }}

    QListWidget {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
        padding: 6px;
        color: {theme.text_primary};
        outline: 0;
    }}

    QListWidget::item {{
        padding: 10px 12px;
        border-radius: 8px;
        margin-bottom: 4px;
        color: {theme.text_primary};
    }}

    QListWidget::item:hover {{
        background-color: {theme.bg_elevated};
    }}

    QListWidget::item:selected {{
        background-color: {theme.accent_light};
        color: {theme.accent_hover if theme.is_dark else theme.accent};
        font-weight: 600;
    }}

    /* === Graphics View (Lightbox Canvas) === */
    QGraphicsView {{
        background-color: {theme.bg_input};
        border: 1px solid {theme.border_subtle};
        border-radius: 12px;
    }}

    /* === Splitter === */
    QSplitter::handle {{
        background-color: transparent;
        width: 8px;
        height: 8px;
    }}

    QSplitter::handle:hover {{
        background-color: {theme.accent_light};
        border-radius: 4px;
    }}

    /* === Progress Bar === */
    QProgressBar {{
        background-color: {theme.bg_input};
        border: 1px solid {theme.border};
        border-radius: 5px;
        height: 8px;
        text-align: center;
    }}

    QProgressBar::chunk {{
        background-color: {theme.accent};
        border-radius: 4px;
    }}

    /* === Scroll Areas & Slim Modern Scrollbars === */
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    QScrollArea > QWidget > QWidget {{
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        background-color: transparent;
        width: 8px;
        margin: 2px 0px;
    }}

    QScrollBar::handle:vertical {{
        background-color: {theme.border};
        min-height: 28px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {theme.accent};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: transparent;
        height: 7px;
        margin: 0px 2px;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {theme.border};
        min-width: 28px;
        border-radius: 3px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {theme.accent};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
        width: 0px;
    }}

    /* === Person Pills === */
    QFrame[class="PersonPill"], QFrame.PersonPill {{
        background-color: {theme.bg_input};
        border: 1px solid {theme.border_subtle};
        border-radius: 25px;
    }}

    QFrame[class="PersonPill"]:hover, QFrame.PersonPill:hover {{
        border-color: {theme.accent};
        background-color: {theme.bg_elevated};
    }}

    QFrame[class="PersonPillSelected"], QFrame.PersonPillSelected {{
        background-color: {theme.accent_light};
        border: 2px solid {theme.accent};
        border-radius: 25px;
    }}

    QFrame[class="PersonPillFlat"] {{
        background-color: transparent;
        border: none;
    }}

    /* === Tooltips & Message Boxes === */
    QToolTip {{
        background-color: {theme.bg_card};
        color: {theme.text_primary};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 11px;
    }}

    QMessageBox {{
        background-color: {theme.bg_card};
        color: {theme.text_primary};
    }}
    """
