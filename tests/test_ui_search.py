import os
from pathlib import Path
import sys

import pytest

# Ensure Qt runs in headless mode
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from podx.models import PodcastSearchResult
from podx.services.config import Config, WhisperSettings, LoggingSettings
from podx.services.subscriptions import SubscriptionService
from podx.services.feeds_meta import FeedsMetaService
from podx.services.rss import RssService
from podx.ui.main import SearchView, SubscriptionListView


class DummyDirectory:
    def search_podcasts(self, term: str):
        assert term == "test"
        return [PodcastSearchResult(name="Test Podcast", feed_url="url", genres=["History"])]


def make_config(tmp_path: Path) -> Config:
    return Config(
        root_dir=tmp_path,
        whisper=WhisperSettings(runner="", model="", extra_args=[]),
        logging=LoggingSettings(),
    )


def test_search_and_subscribe_updates_list(tmp_path):
    app = QApplication.instance() or QApplication([])
    cfg = make_config(tmp_path)
    sub_service = SubscriptionService(cfg)
    feeds_meta = FeedsMetaService(cfg)
    # Provide a dummy RSS service to avoid network during background refresh
    class _DummyRss(RssService):
        def fetch_channel_meta(self, *args, **kwargs):  # type: ignore[override]
            return None, None, None, None, None

    rss = _DummyRss()
    sub_view = SubscriptionListView(sub_service, feeds_meta, rss, on_select=lambda _: None, on_search=lambda: None)
    directory = DummyDirectory()
    search_view = SearchView(
        directory,
        sub_service,
        on_back=lambda: None,
        on_subscribed=lambda _s: sub_view.refresh(),
    )
    search_view.search_input.setText("test")
    search_view.perform_search()
    assert search_view.results.count() == 1
    # Select first result and subscribe via button
    search_view.results.setCurrentRow(0)
    search_view.subscribe_button.click()
    subs = sub_service.list_subscriptions()
    assert len(subs) == 1
    assert subs[0].name == "Test Podcast"
    assert sub_view.model.rowCount() == 1
    idx = sub_view.model.index(0)
    assert sub_view.model.data(idx) == "Test Podcast"
    app.quit()
