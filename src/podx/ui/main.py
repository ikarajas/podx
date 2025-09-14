from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
    QToolBar,
    QWidgetAction,
)

from podx.app import get_config
from podx.services.config import save_config
from podx.models import Subscription
from podx.services.directory import DirectoryService
from podx.services.subscriptions import SubscriptionService
from podx.services.feeds_meta import FeedsMetaService
from podx.services import RssService
from podx.services.episodes_index import EpisodesIndexService
from podx.services.ingestion import IngestionService
from podx.ui.episodes import PodcastView
from .search import SearchView
from .subscriptions_view import SubscriptionListView
from .jobs_view import JobsView
from podx.services.jobs import JobsService




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


if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main())
