import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QEvent, QRect, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem
from PyQt6.QtTest import QSignalSpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from podx.models import FeedEpisode, Subscription
from podx.services.config import Config, WhisperSettings, LoggingSettings
from podx.services.feeds_meta import FeedsMetaService
from podx.services.episodes_index import EpisodesIndexService
from podx.ui.episodes import EpisodeListModel, EpisodeDelegate, PodcastView


def test_model_and_delegate_signal():
    app = QApplication.instance() or QApplication([])
    episodes = [
        FeedEpisode(
            title="Ep1",
            description="Desc",
            published=datetime(2023, 7, 1),
            duration=90,
            artwork_url=None,
        )
    ]
    model = EpisodeListModel(episodes)
    index = model.index(0)
    assert model.data(index, EpisodeListModel.TitleRole) == "Ep1"
    delegate = EpisodeDelegate()
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 300, 100)
    spy = QSignalSpy(delegate.transcribeRequested)
    pos = delegate._icon_rect(option).center()
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    delegate.editorEvent(event, model, option, index)
    assert len(spy) == 1
    assert delegate.sizeHint(option, index).height() >= 80
    app.quit()


class _DummyRss:
    def __init__(self, episodes: list[FeedEpisode]) -> None:
        self._episodes = episodes

    def fetch_episodes(self, _url: str) -> list[FeedEpisode]:
        return self._episodes


def _make_cfg(tmp_path: Path) -> Config:
    return Config(
        root_dir=tmp_path,
        whisper=WhisperSettings(runner="", model="", extra_args=[]),
        logging=LoggingSettings(),
    )


def test_podcast_view_tabs_show_transcript_and_metadata(tmp_path):
    app = QApplication.instance() or QApplication([])
    # Prepare services and index with a transcribed episode
    cfg = _make_cfg(tmp_path)
    feeds_meta = FeedsMetaService(cfg)
    episodes_index = EpisodesIndexService(feeds_meta)
    published = datetime(2023, 7, 1)
    guid = "g-123"
    # Create transcript file and record in episodes index
    key = feeds_meta.get_or_create_key("My Podcast", "http://feed.example")
    episode_dir = tmp_path / key / "ep1"
    episode_dir.mkdir(parents=True, exist_ok=True)
    txt_path = episode_dir / "transcript.txt"
    txt_content = "Hello world transcript\nWith another line."
    txt_path.write_text(txt_content, encoding="utf-8")
    vtt_path = episode_dir / "transcript.vtt"
    vtt_path.write_text("WEBVTT", encoding="utf-8")
    episodes_index.mark_transcribed(
        key,
        title="Episode One",
        published_date=published.isoformat(),
        guid=guid,
        enclosure_url=None,
        episode_dir=episode_dir,
        vtt_path=vtt_path,
        txt_path=txt_path,
    )

    # Rss returns a single episode matching the index entry (by guid)
    episodes = [
        FeedEpisode(
            title="Episode One",
            description="Short description",
            published=published,
            duration=125,
            artwork_url=None,
            guid=guid,
            enclosure_url=None,  # keep None to avoid network during regen tests
            transcribed=False,
        )
    ]
    rss = _DummyRss(episodes)
    # Ingestion service is not used in this test path; pass a dummy object
    ingestion = object()

    view = PodcastView(rss, feeds_meta, episodes_index, ingestion, on_back=lambda: None)
    sub = Subscription(name="My Podcast", feed_url="http://feed.example")
    view.load(sub)
    # Select the first (and only) episode
    idx = view.model.index(0)
    view.list.setCurrentIndex(idx)

    # Right pane metadata
    assert view.episode_title.text() == "Episode One"
    # Meta line should include formatted date and duration 2:05
    assert "Jul" in view.episode_meta.text()
    assert "2:05" in view.episode_meta.text()
    assert view.episode_desc.text() == "Short description"

    # Transcript tab content and header timestamp
    header_text = view.transcript_header_label.text()
    assert header_text.startswith("Transcribed")
    assert txt_content in view.transcript_view.toPlainText()

    # Summary tab placeholder and regeneration click keeps placeholder
    assert view.summary_header_label.text() == "No summary yet"
    assert view.summary_view.toPlainText() == "Summary generation not implemented yet."
    view.summary_regen_btn.click()
    assert view.summary_header_label.text() == "No summary yet"
    assert view.summary_view.toPlainText() == "Summary generation not implemented yet."

    app.quit()


def test_podcast_view_transcript_regenerate_uses_same_handler(tmp_path):
    app = QApplication.instance() or QApplication([])
    cfg = _make_cfg(tmp_path)
    feeds_meta = FeedsMetaService(cfg)
    episodes_index = EpisodesIndexService(feeds_meta)
    published = datetime(2023, 8, 1)
    episodes = [
        FeedEpisode(
            title="Ep",
            description="",
            published=published,
            duration=60,
            artwork_url=None,
            guid="g-1",
            enclosure_url=None,  # no enclosure so handler fails early without network
        )
    ]
    rss = _DummyRss(episodes)
    ingestion = object()
    view = PodcastView(rss, feeds_meta, episodes_index, ingestion, on_back=lambda: None)
    sub = Subscription(name="P", feed_url="http://f")
    # Ensure a meta record exists so view.load() can read description/icon safely
    feeds_meta.get_or_create_key(sub.name, sub.feed_url)
    view.load(sub)
    idx = view.model.index(0)
    view.list.setCurrentIndex(idx)

    # Start from idle
    view.model.setStatus(0, "idle")

    # Click transcript Regenerate
    view.transcript_regen_btn.click()
    # Should end up failed due to missing enclosure (same as delegate path)
    assert view.model.data(idx, EpisodeListModel.StatusRole) == "failed"

    # Reset and trigger via delegate signal
    view.model.setStatus(0, "idle")
    view.delegate.transcribeRequested.emit(idx)
    assert view.model.data(idx, EpisodeListModel.StatusRole) == "failed"

    app.quit()
