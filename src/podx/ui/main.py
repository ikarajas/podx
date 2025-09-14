from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QSize, QRect, QMetaObject
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QMouseEvent, QPalette, QColor, QAction
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
    QToolBar,
    QWidgetAction,
    QPlainTextEdit,
    QFormLayout,
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
from .search import SearchView
from .utils import clean_html
from podx.services.jobs import JobsService, Job


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
        title = clean_html(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.drawText(text_rect.adjusted(0, 4, 0, 0), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft), title)
        # Description (bottom, 2 lines word-wrapped)
        desc = clean_html(index.data(_SubscriptionListModel.DescriptionRole) or "")
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
            # Delete the canonical per-podcast directory resolved via FeedsMetaService
            try:
                pod_dir = self.feeds_meta.podcast_dir(sub.name, sub.feed_url)
                import shutil

                shutil.rmtree(pod_dir, ignore_errors=True)
            except Exception:
                # Best-effort cleanup; ignore failures to keep UI responsive
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


## SearchView moved to podx.ui.search; imported above


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
        self.jobs_service = JobsService(self.ingestion_service)
        self.podcast_view = PodcastView(self.rss_service, self.feeds_meta_service, self.episodes_index_service, self.ingestion_service, on_back=self.show_subscriptions, jobs=self.jobs_service)
        self.stack.addWidget(self.podcast_view)
        self.search_view = SearchView(
            self.directory_service,
            self.subscription_service,
            on_back=self.show_subscriptions,
            on_subscribed=self._on_subscribed,
        )
        self.stack.addWidget(self.search_view)
        self.stack.setCurrentWidget(self.subscriptions_view)
        # Top navigation toolbar
        self._init_toolbar()
        # Apply saved splitter sizes for episodes view
        try:
            v = cfg.ui.episodes_vertical_splitter
            h = cfg.ui.episodes_horizontal_splitter
            self.podcast_view.apply_splitter_sizes(v if v else None, h if h else None)
        except Exception:
            pass

        # Jobs view (wired to JobsService)
        self.jobs_view = JobsView(self.jobs_service)
        self.stack.addWidget(self.jobs_view)
        # Settings placeholder
        self.settings_view = self._make_placeholder_view("Settings — coming soon")
        self.stack.addWidget(self.settings_view)

    def closeEvent(self, event):  # type: ignore[override]
        # Persist current window size to config
        cfg = get_config()
        size = self.size()
        try:
            cfg.ui.window_width = int(size.width())
            cfg.ui.window_height = int(size.height())
            # Save splitter sizes
            try:
                v, h = self.podcast_view.get_splitter_sizes()
                cfg.ui.episodes_vertical_splitter = list(v)
                cfg.ui.episodes_horizontal_splitter = list(h)
            except Exception:
                pass
            save_config(cfg)
        except Exception:
            pass
        return super().closeEvent(event)

    def show_podcast(self, sub: Subscription) -> None:
        self.podcast_view.load(sub)
        self.stack.setCurrentWidget(self.podcast_view)
        self._set_active_nav(None)

    def show_subscriptions(self) -> None:
        self.subscriptions_view.refresh()
        self.stack.setCurrentWidget(self.subscriptions_view)
        self._set_active_nav("subs")

    def show_search(self) -> None:
        self.stack.setCurrentWidget(self.search_view)
        self._set_active_nav("search")

    def show_jobs(self) -> None:
        # Placeholder page for Jobs
        self.stack.setCurrentWidget(self.jobs_view)
        self._set_active_nav("jobs")

    def show_settings(self) -> None:
        # Placeholder page for Settings
        self.stack.setCurrentWidget(self.settings_view)
        self._set_active_nav("settings")

    def _on_subscribed(self, sub: Subscription) -> None:
        # Refresh, select the new subscription, and navigate back
        self.subscriptions_view.refresh()
        self.subscriptions_view.select_by_feed(sub.feed_url)
        self.stack.setCurrentWidget(self.subscriptions_view)
        self._set_active_nav("subs")

    # UI helpers
    def _make_placeholder_view(self, text: str) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addStretch(1)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        layout.addStretch(1)
        return w

    def _init_toolbar(self) -> None:
        tb = QToolBar("Navigation", self)
        # Show text under icons for clarity
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        # Use 24x24 logical icon size; ideal for 1x/2x assets.
        tb.setIconSize(QSize(24, 24))
        tb.setMovable(False)

        style = self.style()
        # Placeholder icons: using standard QStyle icons. You can later replace
        # these with custom assets (recommended SVG 24x24 viewBox with some
        # padding; or PNG at 24x24 and 48x48 for HiDPI) loaded via QIcon.

        self.act_subs = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon), "Subscriptions", self)
        self.act_subs.setStatusTip("Subscriptions (Ctrl+1)")
        self.act_subs.setCheckable(True)
        self.act_subs.triggered.connect(self.show_subscriptions)
        self.act_subs.setShortcut("Ctrl+1")

        self.act_search = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), "Search", self)
        self.act_search.setStatusTip("Search (Ctrl+F)")
        self.act_search.setCheckable(True)
        self.act_search.triggered.connect(self.show_search)
        self.act_search.setShortcut("Ctrl+F")

        self.act_jobs = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Jobs", self)
        self.act_jobs.setStatusTip("Jobs queue (Ctrl+J)")
        self.act_jobs.setCheckable(True)
        self.act_jobs.triggered.connect(self.show_jobs)
        self.act_jobs.setShortcut("Ctrl+J")

        self.act_settings = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Settings", self)
        self.act_settings.setStatusTip("Settings (Ctrl+,)")
        self.act_settings.setCheckable(True)
        self.act_settings.triggered.connect(self.show_settings)
        self.act_settings.setShortcut("Ctrl+,")

        tb.addAction(self.act_subs)
        tb.addAction(self.act_search)
        tb.addAction(self.act_jobs)

        # Spacer to push Settings to the right side
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer_action = QWidgetAction(self)
        spacer_action.setDefaultWidget(spacer)
        tb.addAction(spacer_action)

        tb.addAction(self.act_settings)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self._set_active_nav("subs")

    def _set_active_nav(self, which: str | None) -> None:
        # Keep action checked state in sync with the current view
        for key, act in {
            "subs": self.act_subs,
            "search": self.act_search,
            "jobs": self.act_jobs,
            "settings": self.act_settings,
        }.items():
            act.setChecked(which == key)


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


class JobsView(QWidget):
    """Simple jobs list showing status and percent for background tasks."""

    def __init__(self, jobs: JobsService) -> None:
        super().__init__()
        self.jobs = jobs
        self.items: dict[str, QListWidgetItem] = {}
        self._cache: dict[str, Job] = {}
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)
        # Details panel
        self.details_panel = QWidget()
        form = QFormLayout(self.details_panel)
        self.lbl_title = QLabel("")
        self.lbl_status = QLabel("")
        self.lbl_percent = QLabel("")
        self.lbl_times = QLabel("")
        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        form.addRow("Title:", self.lbl_title)
        form.addRow("Status:", self.lbl_status)
        form.addRow("Progress:", self.lbl_percent)
        form.addRow("Times:", self.lbl_times)
        form.addRow("Result:", self.lbl_result)
        layout.addWidget(self.details_panel)
        self.txt_message = QPlainTextEdit()
        self.txt_message.setReadOnly(True)
        self.txt_message.setPlaceholderText("Job messages and errors will appear here…")
        layout.addWidget(self.txt_message, 1)
        # Subscribe to job updates
        try:
            self.jobs.add_listener(self._on_job_update)
        except Exception:
            pass
        # Selection changed updates details
        self.list.currentItemChanged.connect(self._on_selection_changed)

    def _on_job_update(self, job: Job) -> None:
        def apply():
            item = self.items.get(job.id)
            text = f"{job.type.title()} — {job.podcast}: {job.title}  •  {job.percent}%  •  {job.status}"
            if item is None:
                item = QListWidgetItem(text)
                self.items[job.id] = item
                item.setData(Qt.ItemDataRole.UserRole, job.id)
                self.list.addItem(item)
            else:
                item.setText(text)
            # Cache job
            self._cache[job.id] = job
            cur = self.list.currentItem()
            if cur is not None and cur.data(Qt.ItemDataRole.UserRole) == job.id:
                self._populate_details(job)
        try:
            QMetaObject.invokeMethod(
                self.list, apply, Qt.ConnectionType.QueuedConnection
            )
        except Exception:
            apply()

    def _on_selection_changed(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None = None) -> None:
        if current is None:
            self._clear_details()
            return
        job_id = current.data(Qt.ItemDataRole.UserRole)
        job = self._cache.get(job_id)
        if job is None:
            self._clear_details()
            return
        self._populate_details(job)

    def _populate_details(self, job: Job) -> None:
        self.lbl_title.setText(f"{job.podcast} — {job.title}")
        self.lbl_status.setText(job.status.title())
        self.lbl_percent.setText(f"{job.percent}%")
        parts = []
        if job.created_at:
            parts.append(f"Created: {job.created_at}")
        if job.started_at:
            parts.append(f"Started: {job.started_at}")
        if job.finished_at:
            parts.append(f"Finished: {job.finished_at}")
        self.lbl_times.setText("  |  ".join(parts))
        res = []
        if job.episode_dir:
            res.append(f"Dir: {job.episode_dir}")
        if job.vtt_path:
            res.append(f"VTT: {job.vtt_path}")
        if job.txt_path:
            res.append(f"TXT: {job.txt_path}")
        self.lbl_result.setText("\n".join(res) if res else "—")
        self.txt_message.setPlainText(job.message or "")

    def _clear_details(self) -> None:
        self.lbl_title.clear()
        self.lbl_status.clear()
        self.lbl_percent.clear()
        self.lbl_times.clear()
        self.lbl_result.clear()
        self.txt_message.clear()
if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main())
