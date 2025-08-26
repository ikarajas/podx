from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from podx.app import get_config
from podx.models import Subscription
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


class MainWindow(QMainWindow):
    """Main application window with stacked views."""

    def __init__(self) -> None:
        super().__init__()
        cfg = get_config()
        self.service = SubscriptionService(cfg)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.subscriptions_view = SubscriptionListView(self.service, self.show_podcast, self.show_search)
        self.stack.addWidget(self.subscriptions_view)
        self.podcast_view = QLabel("Podcast view not implemented")
        self.stack.addWidget(self.podcast_view)
        self.search_view = QLabel("Search UI not implemented")
        self.stack.addWidget(self.search_view)
        self.stack.setCurrentWidget(self.subscriptions_view)

    def show_podcast(self, sub: Subscription) -> None:
        self.podcast_view.setText(f"Podcast view for {sub.name}")
        self.stack.setCurrentWidget(self.podcast_view)

    def show_search(self) -> None:
        self.stack.setCurrentWidget(self.search_view)


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main())
