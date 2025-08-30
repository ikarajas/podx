from __future__ import annotations

from typing import List

from PyQt6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QRect,
    QSize,
    Qt,
    QEvent,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPixmap, QPalette
from PyQt6.QtWidgets import (
    QListView,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QHBoxLayout,
)

from ..models import FeedEpisode
from ..services import RssService


class EpisodeListModel(QAbstractListModel):
    TitleRole = Qt.ItemDataRole.UserRole + 1
    DescriptionRole = TitleRole + 1
    DurationRole = TitleRole + 2
    DateRole = TitleRole + 3
    ArtworkRole = TitleRole + 4
    TranscribedRole = TitleRole + 5

    def __init__(self, episodes: List[FeedEpisode] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._episodes = episodes or []

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
        if role == self.ArtworkRole:
            return ep.artwork_url
        if role == self.TranscribedRole:
            return ep.transcribed
        if role == Qt.ItemDataRole.DisplayRole:
            return ep.title
        return None

    def roleNames(self):  # type: ignore[override]
        return {
            int(self.TitleRole): b"title",
            int(self.DescriptionRole): b"description",
            int(self.DurationRole): b"duration",
            int(self.DateRole): b"date",
            int(self.ArtworkRole): b"artwork",
            int(self.TranscribedRole): b"transcribed",
        }

    # Helpers
    def setEpisodes(self, episodes: List[FeedEpisode]) -> None:
        self.beginResetModel()
        self._episodes = episodes
        self.endResetModel()


class EpisodeDelegate(QStyledItemDelegate):
    """Render episodes similar to Apple Podcasts."""

    transcribeRequested = pyqtSignal(QModelIndex)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._icon_size = 24
        self._margin = 8
        style = QWidget().style()
        self._transcribe_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self._done_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)

    # Painting
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        painter.save()
        rect = option.rect
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, option.palette.highlight())
        art_rect = QRect(
            rect.left() + self._margin,
            rect.top() + self._margin,
            rect.height() - 2 * self._margin,
            rect.height() - 2 * self._margin,
        )
        art_url = index.data(EpisodeListModel.ArtworkRole)
        if art_url:
            pix = self._get_pixmap(art_url)
            if pix:
                painter.drawPixmap(
                    art_rect,
                    pix.scaled(art_rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation),
                )
        # Text area
        text_left = art_rect.right() + self._margin
        text_width = rect.width() - (text_left - rect.left()) - self._icon_size - self._margin
        y = rect.top() + self._margin

        # Title
        title = index.data(EpisodeListModel.TitleRole)
        title_font = QFont(option.font)
        title_font.setBold(True)
        title_font.setPointSize(option.font.pointSize() + 2)
        painter.setFont(title_font)
        painter.setPen(option.palette.text().color())
        painter.drawText(QRect(text_left, y, text_width, 24), Qt.TextFlag.TextSingleLine, title)
        y += 24

        # Description
        desc = index.data(EpisodeListModel.DescriptionRole) or ""
        desc_font = QFont(option.font)
        desc_font.setPointSize(option.font.pointSize() - 1)
        painter.setFont(desc_font)
        painter.setPen(QColor("gray"))
        desc_height = 2 * painter.fontMetrics().lineSpacing()
        desc_rect = QRect(text_left, y, text_width, desc_height)
        painter.drawText(desc_rect, Qt.TextFlag.TextWordWrap, desc)
        y = desc_rect.bottom()

        # Meta line
        meta_parts: list[str] = []
        date = index.data(EpisodeListModel.DateRole)
        if date:
            meta_parts.append(date.strftime("%b %d, %Y"))
        duration = index.data(EpisodeListModel.DurationRole)
        if duration is not None:
            minutes = duration // 60
            seconds = duration % 60
            meta_parts.append(f"{minutes:d}:{seconds:02d}")
        meta = " \u2022 ".join(meta_parts)
        meta_font = QFont(option.font)
        meta_font.setPointSize(option.font.pointSize() - 2)
        painter.setFont(meta_font)
        painter.setPen(option.palette.color(QPalette.ColorRole.Mid))
        meta_height = painter.fontMetrics().lineSpacing()
        meta_rect = QRect(text_left, y + self._margin, text_width, meta_height)
        painter.drawText(meta_rect, Qt.TextFlag.TextSingleLine, meta)

        # Transcribe icon
        icon_rect = self._icon_rect(option)
        icon = self._done_icon if index.data(EpisodeListModel.TranscribedRole) else self._transcribe_icon
        icon.paint(painter, icon_rect)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        return QSize(option.rect.width(), 96)

    # Helpers
    def _get_pixmap(self, url: str) -> QPixmap | None:
        pix = self._pixmap_cache.get(url)
        if pix is not None:
            return pix
        p = QPixmap()
        if url.startswith("http"):
            try:
                from urllib.request import urlopen

                with urlopen(url) as resp:
                    data = resp.read()
                p.loadFromData(data)
            except Exception:
                p = None
        else:
            p.load(url)
        if p and not p.isNull():
            self._pixmap_cache[url] = p
            return p
        return None

    def _icon_rect(self, option: QStyleOptionViewItem) -> QRect:
        rect = option.rect
        x = rect.right() - self._margin - self._icon_size
        y = rect.top() + (rect.height() - self._icon_size) // 2
        return QRect(x, y, self._icon_size, self._icon_size)

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractListModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.MouseButtonRelease:
            me: QMouseEvent = event  # type: ignore[assignment]
            if me.button() == Qt.MouseButton.LeftButton and self._icon_rect(option).contains(me.pos()):
                self.transcribeRequested.emit(index)
                return True
        return super().editorEvent(event, model, option, index)


class PodcastView(QWidget):
    """View showing a podcast's episodes."""

    def __init__(self, rss: RssService, on_back) -> None:
        super().__init__()
        self.rss = rss
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(on_back)
        header.addWidget(back)
        header.addStretch(1)
        layout.addLayout(header)
        self.list = QListView()
        self.model = EpisodeListModel()
        self.list.setModel(self.model)
        self.delegate = EpisodeDelegate(self.list)
        self.list.setItemDelegate(self.delegate)
        layout.addWidget(self.list, 1)

    def load(self, sub) -> None:
        episodes = self.rss.fetch_episodes(sub.feed_url)
        self.model.setEpisodes(episodes)
