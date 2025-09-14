from __future__ import annotations

from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QSplitter,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from podx.models import PodcastSearchResult, Subscription
from .utils import fetch_pixmap
from podx.services.directory import DirectoryService
from podx.services.subscriptions import SubscriptionService
from .podcast_list import PodcastListView, PodcastListItem, ListAction
from podx.services import RssService
from .podcast_preview import PodcastPreviewPane


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
        self._rss = RssService()
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
        # Results list (left): generic podcast list without inline actions
        # (we keep the Subscribe button in the detail panel instead)
        actions: list[ListAction] = []
        self.results_list = PodcastListView(
            feeds_meta=None,  # avoid extra RSS refresh during search
            rss=None,
            actions=actions,
            on_open=None,  # no double-click open in search
            on_action=self._on_list_action,
            enable_meta_refresh=False,
        )
        splitter.addWidget(self.results_list)

        # Right-hand preview pane: header + episodes list
        self.preview = PodcastPreviewPane(self._rss)
        splitter.addWidget(self.preview)
        # Expose subscribe button for existing interactions/tests
        self.subscribe_button = self.preview.subscribe_button
        self.subscribe_button.clicked.connect(self.subscribe_current)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        # Selection handler for updating detail view (single click selection)
        self.results_list.list.selectionModel().currentChanged.connect(self._on_selection_changed_index)

        # Back-compat test adapter: expose a tiny API over the list for tests
        class _ResultsAdapter:
            def __init__(self, outer: 'SearchView') -> None:
                self._outer = outer

            def count(self) -> int:
                return self._outer.results_list.model.rowCount()

            def setCurrentRow(self, row: int) -> None:
                if 0 <= row < self._outer.results_list.model.rowCount():
                    idx = self._outer.results_list.model.index(row)
                    self._outer.results_list.list.setCurrentIndex(idx)

        self.results = _ResultsAdapter(self)

    def perform_search(self) -> None:
        term = self.search_input.text().strip()
        if not term:
            return
        podcasts = list(self.directory.search_podcasts(term))
        def _desc_for(p: PodcastSearchResult) -> str | None:
            parts: list[str] = []
            pub = getattr(p, "publisher", None)
            if pub:
                parts.append(pub)
            genres = getattr(p, "genres", None) or []
            if genres:
                parts.append(", ".join(genres))
            return " \u2022 ".join(parts) if parts else None

        items = [
            PodcastListItem(
                name=p.name,
                feed_url=p.feed_url,
                icon_url=getattr(p, "icon_url", None),
                description=_desc_for(p),
                source=p,
            )
            for p in podcasts
        ]
        self.results_list.set_items(items)
        if self.results_list.model.rowCount() > 0:
            # Select first item (single-click selection behavior remains default)
            idx = self.results_list.model.index(0)
            self.results_list.list.setCurrentIndex(idx)

    def _subscribe_from_result(self, podcast: PodcastSearchResult) -> None:
        sub = Subscription(
            name=podcast.name,
            feed_url=podcast.feed_url,
            icon_url=getattr(podcast, "icon_url", None),
        )
        self.subscriptions.add_subscription(sub)
        self.on_subscribed(sub)

    def subscribe_selected(self, item) -> None:
        # Backward-compat wrapper: accept QListWidgetItem-like or PodcastSearchResult
        if hasattr(item, "data"):
            podcast = item.data(Qt.ItemDataRole.UserRole)
        else:
            podcast = item
        if not isinstance(podcast, PodcastSearchResult):
            return
        self._subscribe_from_result(podcast)

    def subscribe_current(self) -> None:
        idx = self.results_list.list.currentIndex()
        if not idx.isValid():
            return
        podcast = self.results_list.model.data(idx, Qt.ItemDataRole.UserRole)
        if isinstance(podcast, PodcastSearchResult):
            self._subscribe_from_result(podcast)

    def _on_selection_changed_index(self, current: QModelIndex, _prev: QModelIndex) -> None:
        if not current.isValid():
            self.preview.clear()
            return
        podcast = self.results_list.model.data(current, Qt.ItemDataRole.UserRole)
        if not isinstance(podcast, PodcastSearchResult):
            self.preview.clear()
            return
        self.preview.load_result(podcast)

    def _clear_detail(self) -> None:
        # Backward compat no-op; preview.clear handles it now
        self.preview.clear()

    def _on_list_action(self, action_id: str, src, _index: QModelIndex) -> None:
        if action_id == "subscribe" and isinstance(src, PodcastSearchResult):
            self._subscribe_from_result(src)

    # Shared pixmap loader lives in ui.utils.fetch_pixmap
