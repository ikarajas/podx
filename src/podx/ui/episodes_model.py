from __future__ import annotations

from typing import List

from PyQt6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt

from ..models import FeedEpisode


class EpisodeListModel(QAbstractListModel):
    TitleRole = Qt.ItemDataRole.UserRole + 1
    DescriptionRole = TitleRole + 1
    DurationRole = TitleRole + 2
    DateRole = TitleRole + 3
    TranscribedRole = TitleRole + 4
    StatusRole = TitleRole + 5  # 'idle' | 'in_progress' | 'failed' | 'transcribed'

    def __init__(self, episodes: List[FeedEpisode] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._episodes = episodes or []
        self._status: list[str] = ["idle"] * len(self._episodes)

    # Model interface
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return len(self._episodes)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if not index.isValid() or not (0 <= index.row() < len(self._episodes)):
            return None
        ep = self._episodes[index.row()]
        if role == self.TitleRole:
            return ep.title
        if role == self.DescriptionRole:
            return ep.description
        if role == self.DurationRole:
            return ep.duration
        if role == self.DateRole:
            return ep.published
        if role == self.TranscribedRole:
            return ep.transcribed
        if role == self.StatusRole:
            row = index.row()
            return self._status[row] if 0 <= row < len(self._status) else "idle"
        if role == Qt.ItemDataRole.ToolTipRole:
            return ep.description or ""
        if role == Qt.ItemDataRole.DisplayRole:
            return ep.title
        return None

    def roleNames(self):  # type: ignore[override]
        return {
            int(self.TitleRole): b"title",
            int(self.DescriptionRole): b"description",
            int(self.DurationRole): b"duration",
            int(self.DateRole): b"date",
            int(self.TranscribedRole): b"transcribed",
            int(self.StatusRole): b"status",
        }

    # Helpers
    def setEpisodes(self, episodes: List[FeedEpisode]) -> None:
        self.beginResetModel()
        self._episodes = episodes
        self._status = ["transcribed" if e.transcribed else "idle" for e in self._episodes]
        self.endResetModel()

    def setStatus(self, row: int, status: str) -> None:
        if not (0 <= row < len(self._episodes)):
            return
        # Ensure status list is sized to episodes
        if len(self._status) < len(self._episodes):
            self._status.extend(["idle"] * (len(self._episodes) - len(self._status)))
        self._status[row] = status
        idx = self.index(row)
        # Emit without roles hint to ensure delegate repaints
        try:
            self.dataChanged.emit(idx, idx)
        except TypeError:
            # Fallback for signatures expecting roles list
            self.dataChanged.emit(idx, idx, [self.StatusRole, self.TranscribedRole])

    def episode_at(self, row: int) -> FeedEpisode | None:
        """Return episode at row or None if out of range."""
        if 0 <= row < len(self._episodes):
            return self._episodes[row]
        return None


__all__ = ["EpisodeListModel"]

