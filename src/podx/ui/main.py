from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QHBoxLayout,
    QSplitter,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from podx.app import get_config
from podx.models import PodcastSearchResult, Subscription
from podx.services.directory import DirectoryService
from podx.services.subscriptions import SubscriptionService
from podx.services import RssService
from podx.ui.episodes import PodcastView


class SubscriptionListView(QWidget):
    """Widget displaying current subscriptions."""

    def __init__(self, service: SubscriptionService, on_select, on_search) -> None:
        super().__init__()
        self.service = service
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(lambda item: on_select(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.list_widget)
        self.search_button = QPushButton("Search Podcasts")
        self.search_button.clicked.connect(on_search)
        layout.addWidget(self.search_button)
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        for sub in self.service.list_subscriptions():
            item = QListWidgetItem(sub.name)
            if sub.icon_url and Path(sub.icon_url).exists():
                item.setIcon(QIcon(sub.icon_url))
            item.setData(Qt.ItemDataRole.UserRole, sub)
            self.list_widget.addItem(item)

    def select_by_feed(self, feed_url: str) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            sub: Subscription = item.data(Qt.ItemDataRole.UserRole)
            if sub.feed_url == feed_url:
                self.list_widget.setCurrentRow(i)
                # Ensure item is visible if list is long
                self.list_widget.scrollToItem(item)
                break


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
        self.subscription_service = SubscriptionService(cfg)
        self.directory_service = DirectoryService(cfg)
        self.rss_service = RssService()
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.subscriptions_view = SubscriptionListView(
            self.subscription_service, self.show_podcast, self.show_search
        )
        self.stack.addWidget(self.subscriptions_view)
        self.podcast_view = PodcastView(self.rss_service, on_back=self.show_subscriptions)
        self.stack.addWidget(self.podcast_view)
        self.search_view = SearchView(
            self.directory_service,
            self.subscription_service,
            on_back=self.show_subscriptions,
            on_subscribed=self._on_subscribed,
        )
        self.stack.addWidget(self.search_view)
        self.stack.setCurrentWidget(self.subscriptions_view)

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
