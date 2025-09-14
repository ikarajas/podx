from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import (
    Qt,
    QAbstractListModel,
    QModelIndex,
    QSize,
    QRect,
    QMetaObject,
    pyqtSignal,
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon
from PyQt6.QtWidgets import (
    QListView,
    QVBoxLayout,
    QWidget,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
)

from podx.services.feeds_meta import FeedsMetaService
from podx.services import RssService
from .utils import clean_html, fetch_pixmap


@dataclass
class PodcastListItem:
    name: str
    feed_url: str
    icon_url: str | None = None
    description: str | None = None
    # Original domain object (e.g., Subscription or PodcastSearchResult)
    source: object | None = None


@dataclass
class ListAction:
    id: str
    icon: QIcon
    tooltip: str = ""


class _PodcastListModel(QAbstractListModel):
    NameRole = Qt.ItemDataRole.UserRole + 1
    IconRole = NameRole + 1
    DescriptionRole = IconRole + 1

    def __init__(self, *, feeds_meta: FeedsMetaService | None = None) -> None:
        super().__init__()
        self._items: list[PodcastListItem] = []
        self._feeds_meta = feeds_meta

    # Qt model interface
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        it = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole or role == self.NameRole:
            return it.name
        if role == self.IconRole:
            return it.icon_url
        if role == self.DescriptionRole:
            return it.description
        if role == Qt.ItemDataRole.UserRole:
            return it.source if it.source is not None else it
        return None

    def roleNames(self):  # type: ignore[override]
        return {int(self.NameRole): b"name", int(self.IconRole): b"icon", int(self.DescriptionRole): b"description"}

    # Convenience APIs used by views
    def setItems(self, items: list[PodcastListItem]) -> None:
        self.beginResetModel()
        # Pre-populate description from cache when available
        if self._feeds_meta is not None:
            enriched: list[PodcastListItem] = []
            for it in items:
                desc = it.description
                if desc is None:
                    meta = self._feeds_meta.get_by_url(it.feed_url)
                    if meta and meta.description:
                        desc = meta.description
                enriched.append(
                    PodcastListItem(
                        name=it.name,
                        feed_url=it.feed_url,
                        icon_url=it.icon_url,
                        description=desc,
                        source=it.source,
                    )
                )
            self._items = enriched
        else:
            self._items = list(items)
        self.endResetModel()

    def setDescription(self, row: int, description: str | None) -> None:
        if 0 <= row < len(self._items):
            self._items[row].description = description
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [self.DescriptionRole])

    def setIconUrl(self, row: int, icon_url: str | None) -> None:
        if 0 <= row < len(self._items):
            self._items[row].icon_url = icon_url
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [self.IconRole])

    def indexOfFeed(self, feed_url: str) -> int:
        for i, it in enumerate(self._items):
            if it.feed_url == feed_url:
                return i
        return -1


class _PodcastDelegate(QStyledItemDelegate):
    actionTriggered = pyqtSignal(str, QModelIndex)

    def __init__(self, actions: list[ListAction], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._margin = 8
        self._thumb = 48
        self._icon_size = 20
        self._item_height = 88
        self._pix_cache: dict[str, QPixmap] = {}
        self._actions = list(actions)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        painter.save()
        rect = option.rect
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, option.palette.highlight())
        # Icon (left)
        icon_rect = rect.adjusted(self._margin, self._margin, 0, 0)
        icon_rect.setWidth(self._thumb)
        icon_rect.setHeight(self._thumb)
        icon_url = index.data(_PodcastListModel.IconRole)
        if icon_url:
            pix = self._pix(icon_url)
            if pix:
                painter.drawPixmap(icon_rect.topLeft(), pix)
        # Text block
        text_left = icon_rect.right() + self._margin
        actions_width = len(self._actions) * (self._icon_size + self._margin)
        if actions_width:
            actions_width += self._margin  # extra breathing room
        text_rect = rect.adjusted(text_left - rect.left(), 0, -actions_width, 0)
        sel = bool(option.state & QStyle.StateFlag.State_Selected)
        title_col = option.palette.highlightedText().color() if sel else option.palette.text().color()
        painter.setPen(title_col)
        title = clean_html(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.drawText(text_rect.adjusted(0, 4, 0, 0), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft), title)
        # Description (optional)
        desc = clean_html(index.data(_PodcastListModel.DescriptionRole) or "")
        if desc:
            snippet = desc.replace("\n", " ")
            base = option.palette.highlightedText().color() if sel else option.palette.text().color()
            sec = QColor(base)
            if not sel:
                sec.setAlpha(200)
            painter.setPen(sec)
            desc_top = text_rect.top() + 24
            # Approximate two lines using the rect height minus title area
            desc_rect = QRect(text_rect.left(), desc_top, text_rect.width(), rect.height() - 28)
            painter.drawText(
                desc_rect,
                int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                snippet,
            )
        # Actions (right)
        y = rect.top() + (rect.height() - self._icon_size) // 2
        x = rect.right() - self._margin - self._icon_size
        for action in self._actions:
            try:
                action.icon.paint(painter, QRect(x, y, self._icon_size, self._icon_size))
            except Exception:
                pass
            x -= self._icon_size + self._margin
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        return QSize(-1, self._item_height)

    def editorEvent(self, event, model, option, index):  # type: ignore[override]
        if event.type() == event.Type.MouseButtonRelease:
            y = option.rect.top() + (option.rect.height() - self._icon_size) // 2
            x = option.rect.right() - self._margin - self._icon_size
            # Traverse in the same order as painted (right to left)
            for action in self._actions:
                r = QRect(x, y, self._icon_size, self._icon_size)
                if event.button() == Qt.MouseButton.LeftButton and r.contains(event.pos()):
                    self.actionTriggered.emit(action.id, index)
                    return True
                x -= self._icon_size + self._margin
        return super().editorEvent(event, model, option, index)

    def _pix(self, url: str) -> QPixmap | None:
        if url in self._pix_cache:
            return self._pix_cache[url]
        p = fetch_pixmap(url)
        if p and not p.isNull():
            scaled = p.scaled(
                self._thumb,
                self._thumb,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._pix_cache[url] = scaled
            return scaled
        return None


class PodcastListView(QWidget):
    """Generic list of podcasts with configurable actions.

    - Renders name, icon and an optional description
    - Emits open and custom actions
    - Optionally refreshes descriptions from RSS metadata cache in background
    """

    def __init__(
        self,
        *,
        feeds_meta: FeedsMetaService | None = None,
        rss: RssService | None = None,
        actions: list[ListAction] | None = None,
        on_open=None,
        on_action=None,
        enable_meta_refresh: bool = False,
    ) -> None:
        super().__init__()
        self._feeds_meta = feeds_meta
        self._rss = rss
        self._on_open = on_open
        self._on_action = on_action
        self._enable_meta_refresh = bool(enable_meta_refresh)
        self._executor = ThreadPoolExecutor(max_workers=2)

        layout = QVBoxLayout(self)
        self.list = QListView()
        self.model = _PodcastListModel(feeds_meta=self._feeds_meta)
        self.list.setModel(self.model)
        # Icons default: only an 'open' action if actions is None.
        # Passing an empty list disables action icons entirely.
        if actions is None:
            style = QWidget().style()
            actions = [ListAction("open", style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "Open")]
        self.delegate = _PodcastDelegate(actions, self.list)
        self.list.setItemDelegate(self.delegate)
        self.delegate.actionTriggered.connect(self._on_action_triggered)
        # Double-click row to open
        self.list.doubleClicked.connect(self._on_double_clicked)
        # Performance knobs
        self.list.setUniformItemSizes(True)
        self.list.setLayoutMode(QListView.LayoutMode.Batched)
        self.list.setBatchSize(256)
        layout.addWidget(self.list)

    # Public API
    def set_items(self, items: list[PodcastListItem]) -> None:
        self.model.setItems(items)
        # Background refresh of stale or missing descriptions
        if not self._enable_meta_refresh or not (self._feeds_meta and self._rss):
            return
        for row, it in enumerate(items):
            key = self._feeds_meta.get_or_create_key(it.name, it.feed_url)
            meta = self._feeds_meta.get_by_url(it.feed_url)
            if self._feeds_meta.is_stale(key) or not (meta and meta.description):
                self._executor.submit(self._refresh_one, row, it, key)

    def select_by_feed(self, feed_url: str) -> None:
        row = self.model.indexOfFeed(feed_url)
        if row >= 0:
            idx = self.model.index(row)
            self.list.setCurrentIndex(idx)
            self.list.scrollTo(idx)

    # Internal
    def _on_double_clicked(self, index: QModelIndex) -> None:
        src = self.model.data(index, Qt.ItemDataRole.UserRole)
        if src is not None and self._on_open:
            try:
                self._on_open(src)
            except Exception:
                pass

    def _on_action_triggered(self, action_id: str, index: QModelIndex) -> None:
        src = self.model.data(index, Qt.ItemDataRole.UserRole)
        if action_id == "open" and self._on_open is not None:
            try:
                self._on_open(src)
            except Exception:
                pass
            return
        if self._on_action is not None:
            try:
                self._on_action(action_id, src, index)
            except Exception:
                pass

    # Worker: refresh a single podcast's metadata
    def _refresh_one(self, row: int, it: PodcastListItem, key: str) -> None:
        assert self._feeds_meta and self._rss
        meta = self._feeds_meta.get_by_url(it.feed_url)
        etag = meta.etag if meta else None
        last_mod = meta.last_modified if meta else None
        try:
            title, description, icon_url, new_etag, new_last_mod = self._rss.fetch_channel_meta(
                it.feed_url, etag=etag, last_modified=last_mod
            )
        except Exception:
            return
        # Update cache
        self._feeds_meta.set_meta(
            key,
            title=title or it.name,
            description=description,
            icon_url=icon_url or it.icon_url,
            etag=new_etag or etag,
            last_modified=new_last_mod or last_mod,
            last_fetch=datetime.now().isoformat(),
        )

        def apply():
            if not (0 <= row < self.model.rowCount()):
                return
            self.model.setDescription(row, description)
            # Update icon if we learned a better one
            if icon_url:
                self.model.setIconUrl(row, icon_url)

        try:
            QMetaObject.invokeMethod(self.list, apply, Qt.ConnectionType.QueuedConnection)
        except Exception:
            apply()


__all__ = [
    "PodcastListItem",
    "ListAction",
    "PodcastListView",
]
