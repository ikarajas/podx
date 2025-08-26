from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from podx.app import get_config
from podx.models import Podcast, Subscription
from podx.services.directory import DirectoryService
from podx.services.subscriptions import SubscriptionService


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
        self.search_input = QLineEdit()
        layout.addWidget(self.search_input)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.perform_search)
        layout.addWidget(self.search_button)
        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self.subscribe_selected)
        layout.addWidget(self.results)
        self.back_button = QPushButton("Back to Subscriptions")
        self.back_button.clicked.connect(on_back)
        layout.addWidget(self.back_button)

    def perform_search(self) -> None:
        term = self.search_input.text().strip()
        self.results.clear()
        if not term:
            return
        for podcast in self.directory.search_podcasts(term):
            item = QListWidgetItem(podcast.name)
            item.setData(Qt.ItemDataRole.UserRole, podcast)
            self.results.addItem(item)

    def subscribe_selected(self, item: QListWidgetItem) -> None:
        podcast: Podcast = item.data(Qt.ItemDataRole.UserRole)
        self.subscriptions.add_subscription(
            Subscription(name=podcast.name, feed_url=podcast.feed_url)
        )
        self.on_subscribed()


class MainWindow(QMainWindow):
    """Main application window with stacked views."""

    def __init__(self) -> None:
        super().__init__()
        cfg = get_config()
        self.subscription_service = SubscriptionService(cfg)
        self.directory_service = DirectoryService(cfg)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.subscriptions_view = SubscriptionListView(
            self.subscription_service, self.show_podcast, self.show_search
        )
        self.stack.addWidget(self.subscriptions_view)
        self.podcast_view = QLabel("Podcast view not implemented")
        self.stack.addWidget(self.podcast_view)
        self.search_view = SearchView(
            self.directory_service,
            self.subscription_service,
            on_back=self.show_subscriptions,
            on_subscribed=self.subscriptions_view.refresh,
        )
        self.stack.addWidget(self.search_view)
        self.stack.setCurrentWidget(self.subscriptions_view)

    def show_podcast(self, sub: Subscription) -> None:
        self.podcast_view.setText(f"Podcast view for {sub.name}")
        self.stack.setCurrentWidget(self.podcast_view)

    def show_subscriptions(self) -> None:
        self.subscriptions_view.refresh()
        self.stack.setCurrentWidget(self.subscriptions_view)

    def show_search(self) -> None:
        self.stack.setCurrentWidget(self.search_view)


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main())
