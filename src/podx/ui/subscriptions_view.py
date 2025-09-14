from __future__ import annotations

from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtWidgets import (
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from podx.models import Subscription
from podx.services.feeds_meta import FeedsMetaService
from podx.services.subscriptions import SubscriptionService
from podx.services import RssService
from .podcast_list import PodcastListView, ListAction, PodcastListItem


class SubscriptionListView(QWidget):
    """Subscriptions wrapper around the generic PodcastListView.

    Keeps public API compatible (model property, refresh, select_by_feed).
    """

    def __init__(self, service: SubscriptionService, feeds_meta: FeedsMetaService, rss: RssService, on_select, on_search) -> None:
        super().__init__()
        self.service = service
        self.feeds_meta = feeds_meta
        self.rss = rss
        self._on_select = on_select
        self._on_search = on_search  # kept for signature compatibility

        layout = QVBoxLayout(self)
        style = self.style()
        actions = [
            ListAction("open", style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "Open"),
            ListAction("delete", style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "Remove"),
        ]
        self._list = PodcastListView(
            feeds_meta=self.feeds_meta,
            rss=self.rss,
            actions=actions,
            on_open=self._handle_open,
            on_action=self._handle_action,
            enable_meta_refresh=True,
        )
        layout.addWidget(self._list)

        # Expose model for tests/back-compat
        self.model = self._list.model

        # Populate initially
        self.refresh()

    def _handle_open(self, src) -> None:
        # src is original Subscription object (by construction below)
        sub: Subscription | None = src if isinstance(src, Subscription) else None
        if sub is None:
            return
        try:
            self._on_select(sub)
        except Exception:
            pass

    def _handle_action(self, action_id: str, src, _index: QModelIndex) -> None:
        if action_id != "delete":
            return
        sub: Subscription | None = src if isinstance(src, Subscription) else None
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
            try:
                pod_dir = self.feeds_meta.podcast_dir(sub.name, sub.feed_url)
                import shutil

                shutil.rmtree(pod_dir, ignore_errors=True)
            except Exception:
                pass
        self.refresh()

    def refresh(self) -> None:
        subs = self.service.list_subscriptions()
        items = [
            PodcastListItem(name=s.name, feed_url=s.feed_url, icon_url=s.icon_url, description=None, source=s)
            for s in subs
        ]
        self._list.set_items(items)

    def select_by_feed(self, feed_url: str) -> None:
        self._list.select_by_feed(feed_url)


__all__ = ["SubscriptionListView"]

