import os
from pathlib import Path
import sys

import pytest

# Ensure Qt runs in headless mode
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from podx.models import Podcast
from podx.services.config import Config, WhisperSettings, LoggingSettings
from podx.services.subscriptions import SubscriptionService
from podx.ui.main import SearchView, SubscriptionListView


class DummyDirectory:
    def search_podcasts(self, term: str):
        assert term == "test"
        return [Podcast(name="Test Podcast", feed_url="url", genres=["History"])]


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
    sub_view = SubscriptionListView(sub_service, on_select=lambda _: None, on_search=lambda: None)
    directory = DummyDirectory()
    search_view = SearchView(directory, sub_service, on_back=lambda: None, on_subscribed=sub_view.refresh)
    search_view.search_input.setText("test")
    search_view.perform_search()
    assert search_view.results.count() == 1
    item = search_view.results.item(0)
    search_view.subscribe_selected(item)
    subs = sub_service.list_subscriptions()
    assert len(subs) == 1
    assert subs[0].name == "Test Podcast"
    assert sub_view.list_widget.count() == 1
    assert sub_view.list_widget.item(0).text() == "Test Podcast"
    app.quit()
