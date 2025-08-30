from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QSize, QRect
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QMouseEvent, QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QHBoxLayout,
    QSplitter,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from podx.app import get_config
from podx.services.config import save_config
from podx.models import PodcastSearchResult, Subscription
from podx.services.directory import DirectoryService
from podx.services.subscriptions import SubscriptionService
from podx.services.feeds_meta import FeedsMetaService
from podx.services import RssService
from podx.services.episodes_index import EpisodesIndexService
from podx.services.ingestion import IngestionService
from podx.ui.episodes import PodcastView


class _SubscriptionListModel(QAbstractListModel):
    NameRole = Qt.ItemDataRole.UserRole + 1
    IconRole = NameRole + 1
    DescriptionRole = IconRole + 1

    def __init__(self, feeds_meta: FeedsMetaService) -> None:
        super().__init__()
        self._subs: list[Subscription] = []
        self._feeds_meta = feeds_meta
        self._descriptions: list[str | None] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return len(self._subs)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if not index.isValid() or not (0 <= index.row() < len(self._subs)):
            return None
        sub = self._subs[index.row()]
        if role == Qt.ItemDataRole.DisplayRole or role == self.NameRole:
            return sub.name
        if role == self.IconRole:
            return sub.icon_url
        if role == self.DescriptionRole:
            return self._descriptions[index.row()] if index.row() < len(self._descriptions) else None
        if role == Qt.ItemDataRole.UserRole:
            return sub
        return None

    def roleNames(self):  # type: ignore[override]
        return {int(self.NameRole): b"name", int(self.IconRole): b"icon", int(self.DescriptionRole): b"description"}

    def setSubscriptions(self, subs: list[Subscription]) -> None:
        self.beginResetModel()
        self._subs = list(subs)
        # populate descriptions from cache
        self._descriptions = []
        for s in self._subs:
            meta = self._feeds_meta.get_by_url(s.feed_url)
            self._descriptions.append(meta.description if meta else None)
        self.endResetModel()

    def indexOfFeed(self, feed_url: str) -> int:
        for i, s in enumerate(self._subs):
            if s.feed_url == feed_url:
                return i
        return -1


class _SubscriptionDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._margin = 8
        self._thumb = 48
        self._icon_size = 20
        self._item_height = 88
        self._pix_cache: dict[str, QPixmap] = {}
        style = QWidget().style()
        self._open_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        self._delete_icon = style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        painter.save()
        rect = option.rect
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, option.palette.highlight())
        # Icon (left)
        icon_rect = rect.adjusted(self._margin, self._margin, 0, 0)
        icon_rect.setWidth(self._thumb)
        icon_rect.setHeight(self._thumb)
        icon_url = index.data(_SubscriptionListModel.IconRole)
        if icon_url:
            pix = self._pix(icon_url)
            if pix:
                painter.drawPixmap(icon_rect.topLeft(), pix)
        # Text block (title + description snippet)
        text_left = icon_rect.right() + self._margin
        right_actions_width = 2 * (self._icon_size + self._margin)
        text_rect = rect.adjusted(text_left - rect.left(), 0, -right_actions_width - self._margin, 0)
        # Title (top)
        sel = bool(option.state & QStyle.StateFlag.State_Selected)
        title_col = option.palette.highlightedText().color() if sel else option.palette.text().color()
        painter.setPen(title_col)
        title = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(text_rect.adjusted(0, 4, 0, 0), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft), title)
        # Description (bottom, 2 lines word-wrapped)
        desc = index.data(_SubscriptionListModel.DescriptionRole) or ""
        if desc:
            snippet = desc.replace("\n", " ")
            # Higher-contrast secondary text; adapt to selection
            base = option.palette.highlightedText().color() if sel else option.palette.text().color()
            sec = QColor(base)
            if not sel:
                sec.setAlpha(200)
            painter.setPen(sec)
            # Allocate approx 2 lines below title
            desc_top = text_rect.top() + 24
            desc_height = min(2 * painter.fontMetrics().lineSpacing(), text_rect.height() - 28)
            desc_rect = QRect(text_rect.left(), desc_top, text_rect.width(), desc_height)
            painter.drawText(desc_rect, Qt.TextFlag.TextWordWrap, snippet)
        # Action icons (right)
        y = rect.top() + (rect.height() - self._icon_size) // 2
        delete_rect = QRect(rect.right() - self._margin - self._icon_size, y, self._icon_size, self._icon_size)
        open_rect = QRect(delete_rect.left() - self._margin - self._icon_size, y, self._icon_size, self._icon_size)
        self._open_icon.paint(painter, open_rect)
        self._delete_icon.paint(painter, delete_rect)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        return QSize(-1, self._item_height)

    def editorEvent(self, event, model, option, index):  # type: ignore[override]
        if event.type() == event.Type.MouseButtonRelease:
            me: QMouseEvent = event  # type: ignore[assignment]
            y = option.rect.top() + (option.rect.height() - self._icon_size) // 2
            delete_rect = QRect(
                option.rect.right() - self._margin - self._icon_size,
                y,
                self._icon_size,
                self._icon_size,
            )
            open_rect = QRect(
                delete_rect.left() - self._margin - self._icon_size,
                y,
                self._icon_size,
                self._icon_size,
            )
            if me.button() == Qt.MouseButton.LeftButton:
                if delete_rect.contains(me.pos()):
                    self.parent().deleteRequested(index)  # type: ignore[attr-defined]
                    return True
                if open_rect.contains(me.pos()):
                    self.parent().openRequested(index)  # type: ignore[attr-defined]
                    return True
        return super().editorEvent(event, model, option, index)

    def _pix(self, url: str) -> QPixmap | None:
        if url in self._pix_cache:
            return self._pix_cache[url]
        p = QPixmap()
        try:
            if Path(url).exists():
                p.load(url)
            elif url.startswith("http"):
                from urllib.request import urlopen

                with urlopen(url) as resp:
                    data = resp.read()
                p.loadFromData(data)
        except Exception:
            return None
        if not p.isNull():
            scaled = p.scaled(
                self._thumb,
                self._thumb,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._pix_cache[url] = scaled
            return scaled
        return None


class SubscriptionListView(QWidget):
    """Widget displaying current subscriptions with actions."""

    def __init__(self, service: SubscriptionService, feeds_meta: FeedsMetaService, rss: RssService, on_select, on_search) -> None:
        super().__init__()
        self.service = service
        self.feeds_meta = feeds_meta
        self.rss = rss
        self._on_select = on_select
        self._executor = ThreadPoolExecutor(max_workers=2)
        layout = QVBoxLayout(self)
        self.list = QListView()
        self.model = _SubscriptionListModel(self.feeds_meta)
        self.list.setModel(self.model)
        # Parent the delegate to this container so it can call our handlers
        self.delegate = _SubscriptionDelegate(self)
        self.list.setItemDelegate(self.delegate)
        # Uniform sizes and batched layout for performance
        self.list.setUniformItemSizes(True)
        self.list.setLayoutMode(QListView.LayoutMode.Batched)
        self.list.setBatchSize(256)
        # Double-click row to open podcast (same as open icon)
        self.list.doubleClicked.connect(self.openRequested)
        layout.addWidget(self.list)
        self.search_button = QPushButton("Search Podcasts")
        self.search_button.clicked.connect(on_search)
        layout.addWidget(self.search_button)
        # Hook delegate events
        # We use methods called by delegate via parent() to avoid signal boilerplate
        self.refresh()

    # Called by delegate
    def openRequested(self, index: QModelIndex) -> None:  # noqa: N802 - Qt style
        sub = self.model.data(index, Qt.ItemDataRole.UserRole)
        if sub:
            self._on_select(sub)

    # Called by delegate
    def deleteRequested(self, index: QModelIndex) -> None:  # noqa: N802 - Qt style
        sub: Subscription | None = self.model.data(index, Qt.ItemDataRole.UserRole)
        if not sub:
            return
        # Confirm subscription removal
        ans = QMessageBox.question(
            self,
            "Remove Subscription",
            f"Remove subscription to '{sub.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.service.remove_subscription(sub.feed_url)
        # Optionally delete local podcast data directory
        ans2 = QMessageBox.question(
            self,
            "Delete Local Data",
            f"Also delete local data for '{sub.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans2 == QMessageBox.StandardButton.Yes:
            pod_dir = self.service.cfg.root_dir / sub.name
            try:
                import shutil

                shutil.rmtree(pod_dir)
            except Exception:
                pass
        self.refresh()

    def refresh(self) -> None:
        subs = self.service.list_subscriptions()
        self.model.setSubscriptions(subs)
        # Background refresh of stale/missing descriptions
        for row, sub in enumerate(subs):
            key = self.feeds_meta.get_or_create_key(sub.name, sub.feed_url)
            if self.feeds_meta.is_stale(key) or not self.model._descriptions[row]:
                self._executor.submit(self._refresh_one, row, sub, key)

    def select_by_feed(self, feed_url: str) -> None:
        row = self.model.indexOfFeed(feed_url)
        if row >= 0:
            idx = self.model.index(row)
            self.list.setCurrentIndex(idx)
            self.list.scrollTo(idx)

    # Worker: refresh a single subscription's metadata
    def _refresh_one(self, row: int, sub: Subscription, key: str) -> None:
        meta = self.feeds_meta.get_by_url(sub.feed_url)
        etag = meta.etag if meta else None
        last_mod = meta.last_modified if meta else None
        try:
            title, description, icon_url, new_etag, new_last_mod = self.rss.fetch_channel_meta(
                sub.feed_url, etag=etag, last_modified=last_mod
            )
        except Exception:
            return
        # Update cache (even if description None, we may update etag/last_fetch)
        self.feeds_meta.set_meta(
            key,
            title=title or sub.name,
            description=description,
            icon_url=icon_url or getattr(sub, "icon_url", None),
            etag=new_etag or etag,
            last_modified=new_last_mod or last_mod,
            last_fetch=datetime.now().isoformat(),
        )
        # Update model description on UI thread via signal/slot; here we schedule to main thread using Qt
        # but to keep it simple, we directly update and emit dataChanged if we're still in same process
        # Find index and emit change
        idx = self.model.index(row)
        # Update model cache
        if row < len(self.model._descriptions):
            self.model._descriptions[row] = description
        self.model.dataChanged.emit(idx, idx, [self.model.DescriptionRole])


class SearchView(QWidget):
    """Widget for searching podcasts and subscribing to them."""

    def __init__(
        self,
        directory: DirectoryService,
        subscriptions: SubscriptionService,
        on_back,
        on_subscribed,
    ) -> None:
        super().__init__()
        self.directory = directory
        self.subscriptions = subscriptions
        self.on_subscribed = on_subscribed
        layout = QVBoxLayout(self)
        # Top-left back button row
        header_row = QHBoxLayout()
        self.back_button = QPushButton("Back to Subscriptions")
        self.back_button.clicked.connect(on_back)
        header_row.addWidget(self.back_button, 0)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        # Search bar row with button on the right
        top_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_button = QPushButton("Search")
        # Keep button only as wide as its contents
        self.search_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.search_button.clicked.connect(self.perform_search)
        # Pressing Enter in the search box triggers search
        self.search_input.returnPressed.connect(self.perform_search)
        top_row.addWidget(self.search_input, 1)
        top_row.addWidget(self.search_button, 0)
        layout.addLayout(top_row)

        # Split view: results list (left) and details (right)
        splitter = QSplitter()
        self.results = QListWidget()
        splitter.addWidget(self.results)

        # Detail panel
        self.detail_panel = QWidget()
        detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_title = QLabel("")
        self.detail_title.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.detail_icon = QLabel("")
        self.detail_icon.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.detail_publisher = QLabel("")
        # Order: title, icon, publisher
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_icon)
        detail_layout.addWidget(self.detail_publisher)
        detail_layout.addStretch(1)
        # Subscribe button at the bottom
        self.subscribe_button = QPushButton("Subscribe")
        self.subscribe_button.clicked.connect(self.subscribe_current)
        detail_layout.addWidget(self.subscribe_button)
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        # Selection handler for updating detail view
        self.results.currentItemChanged.connect(self._on_selection_changed)

    def perform_search(self) -> None:
        term = self.search_input.text().strip()
        self.results.clear()
        if not term:
            return
        podcasts = list(self.directory.search_podcasts(term))
        for podcast in podcasts:
            item = QListWidgetItem(podcast.name)
            item.setData(Qt.ItemDataRole.UserRole, podcast)
            self.results.addItem(item)
        if self.results.count() > 0:
            self.results.setCurrentRow(0)

    def subscribe_selected(self, item: QListWidgetItem) -> None:
        # Deprecated: kept for backward compatibility in tests
        podcast: PodcastSearchResult = item.data(Qt.ItemDataRole.UserRole)
        sub = Subscription(
            name=podcast.name,
            feed_url=podcast.feed_url,
            icon_url=getattr(podcast, "icon_url", None),
        )
        self.subscriptions.add_subscription(sub)
        # Notify with the newly subscribed item
        self.on_subscribed(sub)

    def subscribe_current(self) -> None:
        item = self.results.currentItem()
        if not item:
            return
        self.subscribe_selected(item)

    def _on_selection_changed(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current is None:
            self._clear_detail()
            return
        podcast: PodcastSearchResult = current.data(Qt.ItemDataRole.UserRole)
        # Title
        self.detail_title.setText(podcast.name)
        # Publisher
        pub = getattr(podcast, "publisher", None)
        self.detail_publisher.setText(f"Publisher: {pub}" if pub else "")
        # Icon (download best-effort)
        icon_url = getattr(podcast, "icon_url", None)
        if icon_url:
            pix = self._fetch_pixmap(icon_url)
            if pix is not None:
                # scale to a reasonable size preserving aspect ratio
                self.detail_icon.setPixmap(pix.scaledToWidth(128, Qt.TransformationMode.SmoothTransformation))
            else:
                self.detail_icon.clear()
        else:
            self.detail_icon.clear()

    def _clear_detail(self) -> None:
        self.detail_title.clear()
        self.detail_icon.clear()
        self.detail_publisher.clear()

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


class MainWindow(QMainWindow):
    """Main application window with stacked views."""

    def __init__(self) -> None:
        super().__init__()
        cfg = get_config()
        # Set initial size from config (defaults 1400x800)
        try:
            self.resize(cfg.ui.window_width, cfg.ui.window_height)
        except Exception:
            self.resize(1400, 800)
        self.subscription_service = SubscriptionService(cfg)
        self.feeds_meta_service = FeedsMetaService(cfg)
        self.directory_service = DirectoryService(cfg)
        self.rss_service = RssService()
        self.episodes_index_service = EpisodesIndexService(self.feeds_meta_service)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.subscriptions_view = SubscriptionListView(
            self.subscription_service,
            self.feeds_meta_service,
            self.rss_service,
            self.show_podcast,
            self.show_search,
        )
        self.stack.addWidget(self.subscriptions_view)
        self.ingestion_service = IngestionService(cfg, self.feeds_meta_service, self.episodes_index_service)
        self.podcast_view = PodcastView(self.rss_service, self.feeds_meta_service, self.episodes_index_service, self.ingestion_service, on_back=self.show_subscriptions)
        self.stack.addWidget(self.podcast_view)
        self.search_view = SearchView(
            self.directory_service,
            self.subscription_service,
            on_back=self.show_subscriptions,
            on_subscribed=self._on_subscribed,
        )
        self.stack.addWidget(self.search_view)
        self.stack.setCurrentWidget(self.subscriptions_view)

    def closeEvent(self, event):  # type: ignore[override]
        # Persist current window size to config
        cfg = get_config()
        size = self.size()
        try:
            cfg.ui.window_width = int(size.width())
            cfg.ui.window_height = int(size.height())
            save_config(cfg)
        except Exception:
            pass
        return super().closeEvent(event)

    def show_podcast(self, sub: Subscription) -> None:
        self.podcast_view.load(sub)
        self.stack.setCurrentWidget(self.podcast_view)

    def show_subscriptions(self) -> None:
        self.subscriptions_view.refresh()
        self.stack.setCurrentWidget(self.subscriptions_view)

    def show_search(self) -> None:
        self.stack.setCurrentWidget(self.search_view)

    def _on_subscribed(self, sub: Subscription) -> None:
        # Refresh, select the new subscription, and navigate back
        self.subscriptions_view.refresh()
        self.subscriptions_view.select_by_feed(sub.feed_url)
        self.stack.setCurrentWidget(self.subscriptions_view)


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main())
