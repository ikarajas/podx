"""Aggregated episodes UI exports.

This module re-exports the model, delegate, and view to preserve
backward-compatible imports like `from podx.ui.episodes import PodcastView`.
"""

from __future__ import annotations

from .episodes_model import EpisodeListModel
from .episodes_delegate import EpisodeDelegate
from .podcast_view import PodcastView

__all__ = [
    "EpisodeListModel",
    "EpisodeDelegate",
    "PodcastView",
]

