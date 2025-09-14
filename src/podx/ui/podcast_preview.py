from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PyQt6.QtCore import Qt, QMetaObject
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QScrollArea

from podx.models import PodcastSearchResult
from podx.services import RssService

from .podcast_header import PodcastHeader
from .episodes_pane import PodcastEpisodeList


class PodcastPreviewPane(QWidget):
    """Right-hand preview pane for Search: header + episodes list.

    Read-only: no transcription actions in the episode list.
    """

    def __init__(self, rss: Optional[RssService] = None, parent=None) -> None:
        super().__init__(parent)
        self._rss = rss or RssService()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._load_serial = 0

        layout = QVBoxLayout(self)
        # Header wrapped in a scroll area to cap height for long descriptions
        self.header = PodcastHeader()
        header_scroll = QScrollArea()
        header_scroll.setWidgetResizable(True)
        header_scroll.setWidget(self.header)
        header_scroll.setMaximumHeight(300)
        header_scroll.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(header_scroll)

        # Subscribe button lives in the header's actions row
        self.subscribe_button = QPushButton("Subscribe")
        self.header.actions_layout.addWidget(self.subscribe_button)

        # Episodes list (read-only)
        self.episodes = PodcastEpisodeList(show_action_icon=False)
        layout.addWidget(self.episodes, 1)

    # Public API
    def clear(self) -> None:
        self.header.clear()
        self.episodes.set_episodes([])

    def load_result(self, result: PodcastSearchResult) -> None:
        # Quick header update for responsiveness
        desc = self._fallback_description(result)
        self.header.set_podcast(name=result.name, icon_url=getattr(result, "icon_url", None), description=desc)
        # Async episodes fetch; coalesce by serial
        self._load_serial += 1
        serial = self._load_serial

        def worker():
            try:
                eps = self._rss.fetch_episodes(result.feed_url)
            except Exception:
                eps = []
            def apply():
                if serial != self._load_serial:
                    return
                self.episodes.set_episodes(eps)
                # Select first episode if available
                if self.episodes.model.rowCount() > 0:
                    idx = self.episodes.model.index(0)
                    self.episodes.list.setCurrentIndex(idx)
            try:
                QMetaObject.invokeMethod(self, apply, Qt.ConnectionType.QueuedConnection)
            except Exception:
                apply()

        self._executor.submit(worker)

    # Helpers
    def _fallback_description(self, p: PodcastSearchResult) -> str | None:
        parts: list[str] = []
        pub = getattr(p, "publisher", None)
        if pub:
            parts.append(pub)
        genres = getattr(p, "genres", None) or []
        if genres:
            parts.append(", ".join(genres))
        return " \u2022 ".join(parts) if parts else None


__all__ = ["PodcastPreviewPane"]

