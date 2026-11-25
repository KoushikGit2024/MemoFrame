from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout


class ResetDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reset Workspace Data")
        lay = QVBoxLayout(self)
        msg = QLabel("This deletes the photo index, detected faces, ALL person names, groups and "
                     "cached thumbnails.\nYour photos stay on disk; favourite/keep marks come back "
                     "when the same photos are scanned again.")
        msg.setWordWrap(True)
        lay.addWidget(msg)
        self.chk_sources = QCheckBox("Also forget scanned folders (the 'rescan' list)")
        self.chk_saved = QCheckBox("Also delete saved searches")
        lay.addWidget(self.chk_sources)
        lay.addWidget(self.chk_saved)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type RESET to enable the button")
        lay.addWidget(self.edit)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setEnabled(False)
        self.edit.textChanged.connect(lambda t: self.ok.setEnabled(t.strip() == "RESET"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    @property
    def clear_sources(self) -> bool:
        return self.chk_sources.isChecked()

    @property
    def clear_saved(self) -> bool:
        return self.chk_saved.isChecked()
