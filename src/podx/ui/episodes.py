from __future__ import annotations

from typing import List
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QRect,
    QSize,
    Qt,
    QEvent,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPixmap, QPalette, QFontMetrics
from PyQt6.QtWidgets import (
    QListView,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QToolTip,
)

from ..models import FeedEpisode
from ..services import RssService
from ..services.feeds_meta import FeedsMetaService
from ..services.episodes_index import EpisodesIndexService
from ..services.ingestion import IngestionService


class EpisodeListModel(QAbstractListModel):
    TitleRole = Qt.ItemDataRole.UserRole + 1
    DescriptionRole = TitleRole + 1
    DurationRole = TitleRole + 2
    DateRole = TitleRole + 3
    ArtworkRole = TitleRole + 4
    TranscribedRole = TitleRole + 5
    StatusRole = TitleRole + 6  # 'idle' | 'in_progress' | 'failed' | 'transcribed'

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
        if role == self.ArtworkRole:
            return ep.artwork_url
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
            int(self.ArtworkRole): b"artwork",
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


class EpisodeDelegate(QStyledItemDelegate):
    """Render episodes similar to Apple Podcasts."""

    transcribeRequested = pyqtSignal(QModelIndex)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._icon_size = 24
        self._margin = 8
        self._thumb_px = 80
        self._item_height = 96
        style = QWidget().style()
        self._transcribe_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self._done_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        self._progress_icon = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self._failed_icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)

    # Painting
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, option.palette.highlight())
        # Fixed-size artwork to avoid per-paint scaling
        art_rect = QRect(
            rect.left() + self._margin,
            rect.top() + self._margin,
            self._thumb_px,
            self._thumb_px,
        )
        art_url = index.data(EpisodeListModel.ArtworkRole)
        if art_url:
            pix = self._get_pixmap(art_url)
            if pix:
                # Draw at native size (already scaled once and cached)
                painter.drawPixmap(art_rect.topLeft(), pix)
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
        # Higher-contrast secondary text in dark/light and when selected
        base_sec = option.palette.highlightedText().color() if selected else option.palette.text().color()
        sec = QColor(base_sec)
        if not selected:
            sec.setAlpha(200)
        painter.setPen(sec)
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
        # Date/duration line: ensure strong contrast
        base_meta = option.palette.highlightedText().color() if selected else option.palette.text().color()
        meta_pen = QColor(base_meta)
        if not selected:
            meta_pen.setAlpha(220)
        painter.setPen(meta_pen)
        meta_height = painter.fontMetrics().lineSpacing()
        meta_rect = QRect(text_left, y + self._margin, text_width, meta_height)
        painter.drawText(meta_rect, Qt.TextFlag.TextSingleLine, meta)

        # Transcribe icon
        icon_rect = self._icon_rect(option)
        status = index.data(EpisodeListModel.StatusRole)
        if status == "transcribed" or index.data(EpisodeListModel.TranscribedRole):
            icon = self._done_icon
        elif status == "in_progress":
            icon = self._progress_icon
        elif status == "failed":
            icon = self._failed_icon
        else:
            icon = self._transcribe_icon
        icon.paint(painter, icon_rect)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        # Uniform, fixed height to skip per-item height calculations
        return QSize(-1, self._item_height)

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
            # Scale once to target size and cache to avoid repeated resampling
            scaled = p.scaled(
                self._thumb_px,
                self._thumb_px,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._pixmap_cache[url] = scaled
            return scaled
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
                # Ignore clicks while in progress
                status = index.data(EpisodeListModel.StatusRole)
                if status != "in_progress":
                    self.transcribeRequested.emit(index)
                return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):  # type: ignore[override]
        if event.type() == QEvent.Type.ToolTip:
            desc = index.data(EpisodeListModel.DescriptionRole) or ""
            if desc:
                fm = QFontMetrics(option.font)
                max_w = max(300, int(view.viewport().width() * 0.6))
                text = self._wrap_text(self._strip_html(desc), fm, max_w)
                QToolTip.showText(event.globalPos(), text, view)
                return True
        return super().helpEvent(event, view, option, index)

    def _strip_html(self, text: str) -> str:
        try:
            import re

            return re.sub(r"<[^>]+>", "", text)
        except Exception:
            return text

    def _wrap_text(self, text: str, fm: QFontMetrics, max_width: int) -> str:
        words = text.split()
        if not words:
            return ""
        lines: list[str] = []
        current = words[0]
        for w in words[1:]:
            test = current + " " + w
            if fm.horizontalAdvance(test) <= max_width:
                current = test
            else:
                lines.append(current)
                current = w
        lines.append(current)
        return "\n".join(lines)


class PodcastView(QWidget):
    """View showing a podcast's episodes."""

    # Signal to update UI from worker thread safely
    transcribeFinished = pyqtSignal(int, bool)

    def __init__(self, rss: RssService, feeds_meta: FeedsMetaService, episodes_index: EpisodesIndexService, ingestion: IngestionService, on_back) -> None:
        super().__init__()
        self.rss = rss
        self._feeds_meta = feeds_meta
        self._episodes_index = episodes_index
        self._ingestion = ingestion
        self._insert_chunk = 200
        # Simple single-worker queue to serialize transcriptions
        from concurrent.futures import ThreadPoolExecutor
        self._worker = ThreadPoolExecutor(max_workers=1)
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(on_back)
        header.addWidget(back)
        header.addStretch(1)
        root.addLayout(header)

        # Podcast details (top of window, above splitter). Scrollable with max height.
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setMaximumHeight(300)  # ~50% taller default cap
        details_scroll.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        details = QWidget()
        details_layout = QHBoxLayout(details)
        self.podcast_icon = QLabel("")
        self.podcast_icon.setMinimumSize(64, 64)
        self.podcast_icon.setMaximumSize(96, 96)
        # Preserve aspect ratio: don't stretch the pixmap to the label rect
        self.podcast_icon.setScaledContents(False)
        self.podcast_icon.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        right_box = QVBoxLayout()
        self.podcast_title = QLabel("")
        self.podcast_title.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.podcast_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.podcast_desc = QLabel("")
        self.podcast_desc.setWordWrap(True)
        self.podcast_desc.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.podcast_desc.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        right_box.addWidget(self.podcast_title)
        right_box.addWidget(self.podcast_desc)
        # Keep content anchored to top by consuming extra space at the bottom
        right_box.addStretch(1)
        details_layout.addWidget(self.podcast_icon)
        details_layout.setAlignment(self.podcast_icon, Qt.AlignmentFlag.AlignTop)
        details_layout.addLayout(right_box)
        details_layout.setAlignment(right_box, Qt.AlignmentFlag.AlignTop)
        details_scroll.setWidget(details)
        
        # Nested splitters: vertical (top details + bottom horizontal splitter)
        splitter = QSplitter()
        # Left panel: podcast header + list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.list = QListView()
        self.model = EpisodeListModel()
        self.list.setModel(self.model)
        self.delegate = EpisodeDelegate(self.list)
        self.list.setItemDelegate(self.delegate)
        self.delegate.transcribeRequested.connect(self._on_transcribe)
        # Connect result signal
        self.transcribeFinished.connect(self._on_transcribe_result)
        # Uniform sizes and batched layout
        self.list.setUniformItemSizes(True)
        self.list.setLayoutMode(QListView.LayoutMode.Batched)
        self.list.setBatchSize(256)
        left_layout.addWidget(self.list, 1)
        splitter.addWidget(left_panel)

        # Right panel: transcript display
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.transcript_view = QPlainTextEdit()
        self.transcript_view.setReadOnly(True)
        right_layout.addWidget(self.transcript_view)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        top_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter.addWidget(details_scroll)
        top_splitter.addWidget(splitter)
        # Let list/transcript area take most space
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        # Bias initial sizes to keep details visible but compact
        try:
            top_splitter.setSizes([300, 1200])
        except Exception:
            pass
        root.addWidget(top_splitter, 1)

        # Store splitters for persistence
        self._h_splitter = splitter
        self._v_splitter = top_splitter

        # Selection change to update transcript pane
        self.list.selectionModel().currentChanged.connect(self._on_selection_changed)

    # Splitter persistence helpers
    def apply_splitter_sizes(self, vertical: list[int] | None, horizontal: list[int] | None) -> None:
        try:
            if vertical:
                self._v_splitter.setSizes(vertical)
        except Exception:
            pass
        try:
            if horizontal:
                self._h_splitter.setSizes(horizontal)
        except Exception:
            pass

    def get_splitter_sizes(self) -> tuple[list[int], list[int]]:
        try:
            v = self._v_splitter.sizes()
        except Exception:
            v = []
        try:
            h = self._h_splitter.sizes()
        except Exception:
            h = []
        return v, h

    def _on_transcribe(self, index: QModelIndex) -> None:
        row = index.row()
        if not (0 <= row < self.model.rowCount()):
            return
        self.model.setStatus(row, "in_progress")
        ep = self.model._episodes[row]
        # We need the current subscription context; fetch it by reusing the last loaded key
        # For simplicity, recompute from a minimal Subscription-like object
        # Assume we have the latest 'sub' passed to load stored
        sub = getattr(self, "_current_sub", None)
        if sub is None:
            self.model.setStatus(row, "failed")
            return
        enclosure = getattr(ep, "enclosure_url", None)
        guid = getattr(ep, "guid", None)
        if not enclosure:
            self.model.setStatus(row, "failed")
            return
        # Run download + ingestion in background queue (keeps UI responsive)
        def do_work():
            from urllib.request import urlopen
            import tempfile, os
            try:
                with urlopen(enclosure) as resp:
                    data = resp.read()
                fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)
                with open(tmp_path, "wb") as f:
                    f.write(data)
            except Exception as e:
                return (False, str(e), None)
            try:
                result = self._ingestion.ingest_episode(
                    Path(tmp_path),
                    podcast=sub.name,
                    episode=ep.title,
                    force=False,
                    reporter=None,
                    feed_url=sub.feed_url,
                    enclosure_url=enclosure,
                    guid=guid,
                )
                return (True, None, result)
            except Exception as e:
                return (False, str(e), None)

        fut = self._worker.submit(do_work)

        def _done(_f):
            ok, err, result = _f.result()
            key = self._feeds_meta.get_or_create_key(sub.name, sub.feed_url)
            pub_iso = ep.published.isoformat() if ep.published else None
            # Update index on the worker thread
            if ok and result is not None:
                self._episodes_index.mark_transcribed(
                    key,
                    title=ep.title,
                    published_date=pub_iso or None,
                    guid=guid,
                    enclosure_url=enclosure,
                    episode_dir=result.path,
                    vtt_path=result.transcript.vtt_path,
                    txt_path=result.transcript.txt_path,
                )
            else:
                self._episodes_index.mark_failed(
                    key,
                    title=ep.title,
                    published_date=pub_iso or None,
                    guid=guid,
                    enclosure_url=enclosure,
                    error=str(err or "error"),
                )
            # Emit to UI thread
            try:
                self.transcribeFinished.emit(row, bool(ok and result is not None))
            except Exception:
                # Fallback to timer if signal emission fails
                def update_ui():
                    self._on_transcribe_result(row, bool(ok and result is not None))
                QTimer.singleShot(0, update_ui)

        fut.add_done_callback(_done)

    def _on_transcribe_result(self, row: int, ok: bool) -> None:
        if not (0 <= row < self.model.rowCount()):
            return
        if ok:
            self.model._episodes[row].transcribed = True
            self.model.setStatus(row, "transcribed")
        else:
            self.model.setStatus(row, "failed")
        # Repaint only the affected row
        idx = self.model.index(row)
        rect = self.list.visualRect(idx)
        self.list.viewport().update(rect)
        # Refresh transcript pane if this is the selected row
        cur = self.list.currentIndex()
        if cur.isValid() and cur.row() == row:
            self._update_transcript_for_selection()

    def load(self, sub) -> None:
        self._current_sub = sub
        # Update podcast header
        self.podcast_title.setText(sub.name)
        meta = self._feeds_meta.get_by_url(sub.feed_url)
        desc_text = meta.description or ""
        self.podcast_desc.setText(desc_text)
        # Set icon if available
        icon_url = (meta.icon_url if meta else None) or getattr(sub, "icon_url", None)
        if icon_url:
            pix = self._fetch_pixmap(icon_url)
            if pix is not None:
                # Scale to fit within a square up to 96px, preserving aspect
                target = QSize(self.podcast_icon.maximumWidth(), self.podcast_icon.maximumHeight())
                if target.width() <= 0 or target.height() <= 0:
                    target = QSize(96, 96)
                self.podcast_icon.setPixmap(
                    pix.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
            else:
                self.podcast_icon.clear()
        else:
            self.podcast_icon.clear()
        episodes = self.rss.fetch_episodes(sub.feed_url)
        # Mark transcribed/failed using episodes index for this subscription key
        key = self._feeds_meta.get_or_create_key(sub.name, sub.feed_url)
        statuses: list[str] = []
        for ep in episodes:
            pub_iso = ep.published.isoformat() if ep.published else None
            entry = self._episodes_index.find(key, ep.guid, ep.enclosure_url, pub_iso, ep.title)
            if entry and entry.status == "transcribed":
                ep.transcribed = True
                statuses.append("transcribed")
            elif entry and entry.status == "failed":
                statuses.append("failed")
            else:
                statuses.append("idle")
        # Bulk insert hygiene: clear once, then insert in chunks with updates disabled
        self.model.beginResetModel()
        self.model._episodes = []
        self.model.endResetModel()
        self.list.setUpdatesEnabled(False)
        try:
            for i in range(0, len(episodes), self._insert_chunk):
                chunk = episodes[i : i + self._insert_chunk]
                if not chunk:
                    continue
                first = self.model.rowCount()
                last = first + len(chunk) - 1
                self.model.beginInsertRows(QModelIndex(), first, last)
                self.model._episodes.extend(chunk)
                self.model.endInsertRows()
        finally:
            self.list.setUpdatesEnabled(True)
        # Apply initial statuses
        for i, st in enumerate(statuses):
            if st != "idle":
                self.model.setStatus(i, st)
        # Update transcript pane for current selection
        self._update_transcript_for_selection()

    def _fetch_pixmap(self, url: str) -> QPixmap | None:
        try:
            from urllib.request import urlopen

            with urlopen(url) as resp:
                data = resp.read()
            pix = QPixmap()
            if pix.loadFromData(data):
                return pix
        except Exception:
            return None
        return None

    def _on_selection_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        self._update_transcript_for_selection()

    def _update_transcript_for_selection(self) -> None:
        idx = self.list.currentIndex()
        if not idx.isValid():
            self.transcript_view.setPlainText("")
            return
        row = idx.row()
        if not (0 <= row < len(self.model._episodes)):
            self.transcript_view.setPlainText("")
            return
        ep = self.model._episodes[row]
        sub = getattr(self, "_current_sub", None)
        if sub is None:
            self.transcript_view.setPlainText("")
            return
        key = self._feeds_meta.get_or_create_key(sub.name, sub.feed_url)
        pub_iso = ep.published.isoformat() if ep.published else None
        entry = self._episodes_index.find(key, getattr(ep, "guid", None), getattr(ep, "enclosure_url", None), pub_iso, ep.title)
        if entry and entry.status == "transcribed" and entry.txt_path:
            try:
                text = Path(entry.txt_path).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = "(Could not read transcript file)"
            self.transcript_view.setPlainText(text)
        else:
            self.transcript_view.setPlainText(
                "No transcript yet. Select an episode and click the transcribe icon to generate it."
            )
