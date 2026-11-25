"""Play the video half of a Live Photo."""
from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class LivePhotoDialog(QDialog):
    def __init__(self, video_path: str, parent=None) -> None:
        super().__init__(parent)
        from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer          # may raise ImportError
        from PyQt6.QtMultimediaWidgets import QVideoWidget
        self.setWindowTitle("Live Photo")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        video = QVideoWidget()
        video.setMinimumSize(640, 440)
        lay.addWidget(video, 1)
        self.status = QLabel("")
        self.status.setProperty("class", "Dim")
        lay.addWidget(self.status)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(video)
        self.player.errorOccurred.connect(
            lambda _err, msg: self.status.setText(f"Cannot play this video here: {msg}"))
        self.player.setSource(QUrl.fromLocalFile(video_path))
        row = QHBoxLayout()
        replay = QPushButton("Replay")
        replay.clicked.connect(lambda: (self.player.setPosition(0), self.player.play()))
        close = QPushButton("Close")
        close.setProperty("class", "Secondary")
        close.clicked.connect(self.accept)
        row.addWidget(replay)
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)
        self.player.play()

    def done(self, result: int) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        super().done(result)
