import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QEvent, QRect, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem
from PyQt6.QtTest import QSignalSpy

from podx.models import FeedEpisode
from podx.ui.episodes import EpisodeListModel, EpisodeDelegate


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
    assert spy.count() == 1
    assert delegate.sizeHint(option, index).height() >= 80
    app.quit()
