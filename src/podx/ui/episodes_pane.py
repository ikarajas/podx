from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListView

from .episodes_model import EpisodeListModel
from .episodes_delegate import EpisodeDelegate


class PodcastEpisodeList(QWidget):
    """Wrapper around episodes list model/delegate with sane defaults."""

    def __init__(self, *, show_action_icon: bool = True, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.list = QListView()
        self.model = EpisodeListModel()
        self.list.setModel(self.model)
        self.delegate = EpisodeDelegate(self.list, show_action_icon=show_action_icon)
        self.list.setItemDelegate(self.delegate)
        # Performance knobs
        self.list.setUniformItemSizes(True)
        self.list.setLayoutMode(QListView.LayoutMode.Batched)
        self.list.setBatchSize(256)
        layout.addWidget(self.list)

    def set_episodes(self, episodes) -> None:
        self.model.setEpisodes(list(episodes))


__all__ = ["PodcastEpisodeList"]

