from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QHBoxLayout,
    QSplitter,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from podx.models import PodcastSearchResult, Subscription
from .utils import fetch_pixmap
from podx.services.directory import DirectoryService
from podx.services.subscriptions import SubscriptionService


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
            pix = fetch_pixmap(icon_url)
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

    # Shared pixmap loader lives in ui.utils.fetch_pixmap
