from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy

from .utils import fetch_pixmap


class PodcastHeader(QWidget):
    """Reusable header showing podcast icon, title and description.

    Provides an actions row on the right side of the title for context buttons.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        self.icon = QLabel("")
        self.icon.setMinimumSize(64, 64)
        self.icon.setMaximumSize(96, 96)
        self.icon.setScaledContents(False)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        right_box = QVBoxLayout()
        title_row = QHBoxLayout()
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        # Right-aligned actions placeholder
        self._actions_container = QWidget()
        self._actions_container.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self._actions_layout = QHBoxLayout(self._actions_container)
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        title_row.addWidget(self.title, 1)
        title_row.addWidget(self._actions_container, 0)

        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.description.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        right_box.addLayout(title_row)
        right_box.addWidget(self.description)
        right_box.addStretch(1)

        root.addWidget(self.icon)
        root.addLayout(right_box)

    # Public API
    @property
    def actions_layout(self):
        return self._actions_layout

    def clear(self) -> None:
        self.title.setText("")
        self.description.setText("")
        self.icon.clear()

    def set_podcast(self, *, name: str, icon_url: str | None, description: str | None) -> None:
        self.title.setText(name or "")
        self.description.setText(description or "")
        if icon_url:
            pix = fetch_pixmap(icon_url)
            if pix is not None:
                target = QSize(self.icon.maximumWidth(), self.icon.maximumHeight())
                if target.width() <= 0 or target.height() <= 0:
                    target = QSize(96, 96)
                self.icon.setPixmap(
                    pix.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
                return
        self.icon.clear()


__all__ = ["PodcastHeader"]

