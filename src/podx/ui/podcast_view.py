from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QModelIndex, QSize, Qt, QMetaObject, pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QListView,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
)

from .episodes_model import EpisodeListModel
from .episodes_delegate import EpisodeDelegate
from .episodes_pane import PodcastEpisodeList
from .utils import clean_html, format_episode_meta, fetch_pixmap
from ..services import RssService
from ..services.feeds_meta import FeedsMetaService
from ..services.episodes_index import EpisodesIndexService
from ..services.ingestion import IngestionService
from ..services.jobs import JobsService, Job


def _fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y %H:%M")
    except Exception:
        return iso


class PodcastView(QWidget):
    """View showing a podcast's episodes.

    Shared component: used in the main UI with transcription enabled, and
    can be embedded in other contexts (e.g., search) in a read-only mode.
    Toggle behavior via ``enable_transcription``.
    """

    # Signal to update UI from worker thread safely
    transcribeFinished = pyqtSignal(int, bool)

    def __init__(
        self,
        rss: RssService,
        feeds_meta: FeedsMetaService,
        episodes_index: EpisodesIndexService,
        ingestion: IngestionService,
        on_back,
        jobs: JobsService | None = None,
        *,
        enable_transcription: bool = True,
    ) -> None:
        super().__init__()
        self.rss = rss
        self._feeds_meta = feeds_meta
        self._episodes_index = episodes_index
        self._ingestion = ingestion
        self._jobs = jobs
        self._enable_transcription = bool(enable_transcription)
        self._insert_chunk = 200
        self._default_art_url: str | None = None
        # Map job id -> row index for UI updates
        self._job_rows: dict[str, int] = {}
        root = QVBoxLayout(self)

        # Podcast details (top of window, above splitter). Scrollable with max height.
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setMaximumHeight(300)  # ~50% taller default cap
        details_scroll.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        details = QWidget()
        details_layout = QHBoxLayout(details)
        self.podcast_icon = QLabel("")
        self.podcast_icon.setMinimumSize(64, 64)
        self.podcast_icon.setMaximumSize(96, 96)
        # Preserve aspect ratio: don't stretch the pixmap to the label rect
        self.podcast_icon.setScaledContents(False)
        self.podcast_icon.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        right_box = QVBoxLayout()
        self.podcast_title = QLabel("")
        self.podcast_title.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.podcast_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.podcast_desc = QLabel("")
        self.podcast_desc.setWordWrap(True)
        self.podcast_desc.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.podcast_desc.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        right_box.addWidget(self.podcast_title)
        right_box.addWidget(self.podcast_desc)
        # Keep content anchored to top by consuming extra space at the bottom
        right_box.addStretch(1)
        details_layout.addWidget(self.podcast_icon)
        details_layout.setAlignment(self.podcast_icon, Qt.AlignmentFlag.AlignTop)
        details_layout.addLayout(right_box)
        details_layout.setAlignment(right_box, Qt.AlignmentFlag.AlignTop)
        details_scroll.setWidget(details)

        # Nested splitters: vertical (top details + bottom horizontal splitter)
        splitter = QSplitter()
        # Left panel: podcast header + list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        # Episodes list (wrapped for reuse)
        self._episodes_pane = PodcastEpisodeList(show_action_icon=self._enable_transcription)
        self.list = self._episodes_pane.list
        self.model = self._episodes_pane.model
        self.delegate = self._episodes_pane.delegate
        # Delegate click triggers a normal transcription (no force)
        if self._enable_transcription:
            self.delegate.transcribeRequested.connect(lambda idx: self._on_transcribe(idx, force=False))
            # Connect result signal only when we support transcription
            self.transcribeFinished.connect(self._on_transcribe_result)
        left_layout.addWidget(self._episodes_pane, 1)
        splitter.addWidget(left_panel)

        # Right panel: episode header + tabs (Transcript, Summary)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Episode header (artwork + title + meta + description)
        self.episode_header = QWidget()
        eh_layout = QHBoxLayout(self.episode_header)
        self.episode_art = QLabel("")
        # Keep icon fully visible: fix width/height to avoid horizontal cropping
        self.episode_art.setMinimumSize(120, 120)
        self.episode_art.setMaximumSize(120, 120)
        self.episode_art.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.episode_art.setScaledContents(False)
        self.episode_art.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        eh_right = QVBoxLayout()
        self.episode_title = QLabel("")
        self.episode_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.episode_meta = QLabel("")
        pal = self.episode_meta.palette()
        sec = pal.color(QPalette.ColorRole.WindowText)
        sec.setAlpha(200)
        self.episode_meta.setStyleSheet(f"color: {sec.name()}; font-size: 11px;")
        self.episode_desc = QLabel("")
        self.episode_desc.setWordWrap(True)
        eh_right.addWidget(self.episode_title)
        eh_right.addWidget(self.episode_meta)
        eh_right.addWidget(self.episode_desc)
        eh_right.addStretch(1)
        eh_layout.addWidget(self.episode_art)
        eh_layout.addLayout(eh_right)

        # Tabs container
        self.tabs = QTabWidget()

        # Transcript tab
        transcript_tab = QWidget()
        t_layout = QVBoxLayout(transcript_tab)
        t_head = QHBoxLayout()
        self.transcript_header_label = QLabel("")
        self.transcript_regen_btn = QPushButton("Regenerate")
        # Regenerate should force re-transcription even if files exist
        if self._enable_transcription:
            self.transcript_regen_btn.clicked.connect(lambda: self._on_transcribe(self.list.currentIndex(), force=True))
        else:
            self.transcript_regen_btn.hide()
        t_head.addWidget(self.transcript_header_label)
        t_head.addStretch(1)
        t_head.addWidget(self.transcript_regen_btn)
        t_layout.addLayout(t_head)
        self.transcript_view = QPlainTextEdit()
        self.transcript_view.setReadOnly(True)
        t_layout.addWidget(self.transcript_view)
        self.tabs.addTab(transcript_tab, "Transcript")

        # Summary tab (placeholder until summaries exist)
        summary_tab = QWidget()
        s_layout = QVBoxLayout(summary_tab)
        s_head = QHBoxLayout()
        self.summary_header_label = QLabel("")
        self.summary_regen_btn = QPushButton("Summarise")
        if self._enable_transcription:
            self.summary_regen_btn.clicked.connect(self._on_generate_summary)
        else:
            self.summary_regen_btn.hide()
        s_head.addWidget(self.summary_header_label)
        s_head.addStretch(1)
        s_head.addWidget(self.summary_regen_btn)
        s_layout.addLayout(s_head)
        self.summary_view = QPlainTextEdit()
        self.summary_view.setReadOnly(True)
        s_layout.addWidget(self.summary_view)
        self.tabs.addTab(summary_tab, "Summary")

        # Wrap episode header in a scroll area to keep header compact while
        # allowing long descriptions to be scrollable.
        self.episode_header_scroll = QScrollArea()
        self.episode_header_scroll.setWidgetResizable(True)
        self.episode_header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.episode_header_scroll.setWidget(self.episode_header)
        # Tall enough to show full icon height; text can scroll
        try:
            self.episode_header_scroll.setFixedHeight(self.episode_art.maximumHeight() + 20)
        except Exception:
            pass
        # Ensure the icon sits at the top within the header
        try:
            eh_layout.setAlignment(self.episode_art, Qt.AlignmentFlag.AlignTop)
        except Exception:
            pass

        right_layout.addWidget(self.episode_header_scroll)
        right_layout.addWidget(self.tabs)
        if not self._enable_transcription:
            # Hide transcript/summary section in read-only browse mode
            self.tabs.hide()
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        top_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter.addWidget(details_scroll)
        top_splitter.addWidget(splitter)
        # Let list/transcript area take most space
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        # Bias initial sizes to keep details visible but compact
        try:
            top_splitter.setSizes([300, 1200])
        except Exception:
            pass
        root.addWidget(top_splitter, 1)

        # Store splitters for persistence
        self._h_splitter = splitter
        self._v_splitter = top_splitter

        # Selection change to update episode header and tabs
        self.list.selectionModel().currentChanged.connect(self._on_selection_changed)
        # Listen to JobsService updates if available (UI-thread marshal in handler)
        if self._enable_transcription and self._jobs is not None:
            try:
                self._jobs.add_listener(self._on_job_update)
            except Exception:
                pass

    # Splitter persistence helpers
    def apply_splitter_sizes(self, vertical: list[int] | None, horizontal: list[int] | None) -> None:
        try:
            if vertical:
                self._v_splitter.setSizes(vertical)
        except Exception:
            pass
        try:
            if horizontal:
                self._h_splitter.setSizes(horizontal)
        except Exception:
            pass

    def get_splitter_sizes(self) -> tuple[list[int], list[int]]:
        try:
            v = self._v_splitter.sizes()
        except Exception:
            v = []
        try:
            h = self._h_splitter.sizes()
        except Exception:
            h = []
        return v, h

    def _on_transcribe(self, index: QModelIndex, *, force: bool = False) -> None:
        row = index.row()
        if not (0 <= row < self.model.rowCount()):
            return
        self.model.setStatus(row, "in_progress")
        ep = self.model.episode_at(row)
        if ep is None:
            self.model.setStatus(row, "failed")
            return
        # We need the current subscription context; fetch it by reusing the last loaded key
        # For simplicity, recompute from a minimal Subscription-like object
        # Assume we have the latest 'sub' passed to load stored
        sub = getattr(self, "_current_sub", None)
        if sub is None:
            self.model.setStatus(row, "failed")
            return
        enclosure = getattr(ep, "enclosure_url", None)
        guid = getattr(ep, "guid", None)
        if not enclosure or self._jobs is None:
            self.model.setStatus(row, "failed")
            return
        pub_iso = ep.published.isoformat() if getattr(ep, "published", None) else None
        try:
            job_id = self._jobs.enqueue_transcription(
                podcast=sub.name,
                title=ep.title,
                feed_url=sub.feed_url,
                enclosure_url=enclosure,
                guid=guid,
                published_date=pub_iso,
                force=bool(force),
            )
            self._job_rows[job_id] = row
        except Exception:
            self.model.setStatus(row, "failed")
            return

    def _on_transcribe_result(self, row: int, ok: bool) -> None:
        if not (0 <= row < self.model.rowCount()):
            return
        self.model.mark_transcribed(row, ok)
        # Repaint only the affected row
        idx = self.model.index(row)
        rect = self.list.visualRect(idx)
        self.list.viewport().update(rect)
        # Refresh transcript/summary panes if this is the selected row
        cur = self.list.currentIndex()
        if cur.isValid() and cur.row() == row:
            self._update_transcript_for_selection()
            self._update_summary_for_selection()

    # Listener for JobsService updates
    def _on_job_update(self, job: Job) -> None:
        def apply():
            row = self._job_rows.get(job.id)
            if row is None or not (0 <= row < self.model.rowCount()):
                return
            cur = self.list.currentIndex()
            is_selected = cur.isValid() and cur.row() == row
            if job.type == "summarize":
                if job.status == "succeeded" and is_selected:
                    self._update_summary_for_selection()
                elif job.status == "failed" and is_selected:
                    self.summary_header_label.setText("Summary failed")
                    self.summary_view.setPlainText(
                        f"Summary generation failed.\n\nReason: {job.message or 'Unknown error'}\n\n"
                        "Click Regenerate to try again."
                    )
            else:
                if job.status == "running":
                    self.model.setStatus(row, "in_progress")
                elif job.status == "succeeded":
                    self.model.mark_transcribed(row, True)
                    if is_selected:
                        self._update_transcript_for_selection()
                        self._update_summary_for_selection()
                elif job.status == "failed":
                    self.model.mark_transcribed(row, False)
                    if is_selected:
                        self._update_transcript_for_selection()
        try:
            QMetaObject.invokeMethod(self.list, apply, Qt.ConnectionType.QueuedConnection)
        except Exception:
            apply()

    def load(self, sub) -> None:
        self._current_sub = sub
        # Update podcast header
        self.podcast_title.setText(sub.name)
        meta = self._feeds_meta.get_by_url(sub.feed_url)
        desc_text = meta.description or ""
        self.podcast_desc.setText(desc_text)
        # Set icon if available
        icon_url = (meta.icon_url if meta else None) or getattr(sub, "icon_url", None)
        if icon_url:
            pix = fetch_pixmap(icon_url)
            if pix is not None:
                # Scale to fit within a square up to 96px, preserving aspect
                target = QSize(self.podcast_icon.maximumWidth(), self.podcast_icon.maximumHeight())
                if target.width() <= 0 or target.height() <= 0:
                    target = QSize(96, 96)
                self.podcast_icon.setPixmap(
                    pix.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
            else:
                self.podcast_icon.clear()
        else:
            self.podcast_icon.clear()
        # Store default artwork URL for episode header fallback
        self._default_art_url = icon_url if icon_url else None
        # Episode list no longer displays per-item artwork; header shows art.
        episodes = self.rss.fetch_episodes(sub.feed_url)
        # Mark transcribed/failed using episodes index for this subscription key
        key = self._feeds_meta.get_or_create_key(sub.name, sub.feed_url)
        statuses: list[str] = []
        for ep in episodes:
            pub_iso = ep.published.isoformat() if ep.published else None
            entry = self._episodes_index.find(key, ep.guid, ep.enclosure_url, pub_iso, ep.title)
            if entry and entry.status == "transcribed":
                ep.transcribed = True
                statuses.append("transcribed")
            elif entry and entry.status == "failed":
                statuses.append("failed")
            else:
                statuses.append("idle")
        # Bulk insert hygiene: clear once, then insert in chunks with updates disabled
        self.model.beginResetModel()
        self.model._episodes = []
        # Reset statuses to avoid bleed-through from previous podcast
        self.model._status = []
        self.model.endResetModel()
        self.list.setUpdatesEnabled(False)
        try:
            for i in range(0, len(episodes), self._insert_chunk):
                chunk = episodes[i : i + self._insert_chunk]
                if not chunk:
                    continue
                first = self.model.rowCount()
                last = first + len(chunk) - 1
                self.model.beginInsertRows(QModelIndex(), first, last)
                self.model._episodes.extend(chunk)
                # Grow statuses with idle defaults for new rows
                self.model._status.extend(["idle"] * len(chunk))
                self.model.endInsertRows()
        finally:
            self.list.setUpdatesEnabled(True)
        # Apply initial statuses
        for i, st in enumerate(statuses):
            if st != "idle":
                self.model.setStatus(i, st)
        # Update panes for current selection
        self._update_episode_header_for_selection()
        self._update_transcript_for_selection()
        self._update_summary_for_selection()

    def _on_selection_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        self.tabs.setCurrentIndex(0)
        self._update_episode_header_for_selection()
        self._update_transcript_for_selection()
        self._update_summary_for_selection()

    def _update_transcript_for_selection(self) -> None:
        idx = self.list.currentIndex()
        if not idx.isValid():
            self.transcript_header_label.setText("No episode selected")
            self.transcript_view.setPlainText("")
            return
        row = idx.row()
        if not (0 <= row < self.model.rowCount()):
            self.transcript_header_label.setText("")
            self.transcript_view.setPlainText("")
            return
        ep = self.model.episode_at(row)
        if ep is None:
            self.transcript_header_label.setText("")
            self.transcript_view.setPlainText("")
            return
        sub = getattr(self, "_current_sub", None)
        if sub is None:
            self.transcript_header_label.setText("")
            self.transcript_view.setPlainText("")
            return
        key = self._feeds_meta.get_or_create_key(sub.name, sub.feed_url)
        pub_iso = ep.published.isoformat() if ep.published else None
        entry = self._episodes_index.find(
            key,
            getattr(ep, "guid", None),
            getattr(ep, "enclosure_url", None),
            pub_iso,
            ep.title,
        )
        if entry and entry.status == "transcribed" and entry.txt_path:
            try:
                text = Path(entry.txt_path).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = "(Could not read transcript file)"
            ts = entry.updated_at or entry.created_at or ""
            hdr = f"Transcribed: {_fmt_ts(ts)}" if ts else "Transcribed"
            self.transcript_header_label.setText(hdr)
            self.transcript_view.setPlainText(text)
            self.transcript_regen_btn.setText("Regenerate")
        elif entry and entry.status == "failed":
            ts = entry.updated_at or entry.created_at or ""
            hdr = f"Transcription failed: {_fmt_ts(ts)}" if ts else "Transcription failed"
            self.transcript_header_label.setText(hdr)
            reason = entry.error or "Unknown error"
            self.transcript_view.setPlainText(
                f"Transcription failed.\n\nReason: {reason}\n\nClick Transcribe to try again."
            )
            self.transcript_regen_btn.setText("Transcribe")
        else:
            self.transcript_header_label.setText("No transcript yet")
            self.transcript_view.setPlainText(
                "No transcript yet. Select an episode and click the transcribe icon to generate it."
            )
            self.transcript_regen_btn.setText("Transcribe")

    def _update_summary_for_selection(self) -> None:
        idx = self.list.currentIndex()
        if not idx.isValid():
            self.summary_header_label.setText("No episode selected")
            self.summary_view.setPlainText("")
            return
        row = idx.row()
        if not (0 <= row < self.model.rowCount()):
            self.summary_header_label.setText("")
            self.summary_view.setPlainText("")
            return
        ep = self.model.episode_at(row)
        if ep is None:
            self.summary_header_label.setText("")
            self.summary_view.setPlainText("")
            return
        sub = getattr(self, "_current_sub", None)
        if sub is None:
            self.summary_header_label.setText("")
            self.summary_view.setPlainText("")
            return
        key = self._feeds_meta.get_or_create_key(sub.name, sub.feed_url)
        pub_iso = ep.published.isoformat() if ep.published else None
        entry = self._episodes_index.find(
            key,
            getattr(ep, "guid", None),
            getattr(ep, "enclosure_url", None),
            pub_iso,
            ep.title,
        )
        if entry and entry.summary_path:
            try:
                text = Path(entry.summary_path).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = "(Could not read summary file)"
            ts = entry.summary_updated_at or ""
            hdr = f"Summarised: {_fmt_ts(ts)}" if ts else "Summarised"
            self.summary_header_label.setText(hdr)
            self.summary_view.setPlainText(text)
            self.summary_regen_btn.setText("Regenerate")
        elif entry and entry.status == "transcribed":
            self.summary_header_label.setText("No summary yet")
            self.summary_view.setPlainText(
                "No summary yet. Click Summarise to generate one."
            )
            self.summary_regen_btn.setText("Summarise")
        else:
            self.summary_header_label.setText("No summary yet")
            self.summary_view.setPlainText(
                "No transcript yet. Transcribe this episode first, then click Summarise."
            )
            self.summary_regen_btn.setText("Summarise")

    def _update_episode_header_for_selection(self) -> None:
        idx = self.list.currentIndex()
        if not idx.isValid():
            self.episode_title.setText("")
            self.episode_meta.setText("")
            self.episode_desc.setText("")
            self.episode_art.clear()
            return
        row = idx.row()
        if not (0 <= row < self.model.rowCount()):
            self.episode_title.setText("")
            self.episode_meta.setText("")
            self.episode_desc.setText("")
            self.episode_art.clear()
            return
        ep = self.model.episode_at(row)
        if ep is None:
            self.episode_title.setText("")
            self.episode_meta.setText("")
            self.episode_desc.setText("")
            self.episode_art.clear()
            return
        self.episode_title.setText(ep.title or "")
        # Meta: date + duration
        self.episode_meta.setText(
            format_episode_meta(ep.published, ep.duration)
        )
        self.episode_desc.setText(clean_html(ep.description or ""))
        # Artwork
        # Artwork with fallback to podcast default icon
        pix = None
        if ep.artwork_url:
            pix = fetch_pixmap(ep.artwork_url)
        if pix is None and self._default_art_url:
            pix = fetch_pixmap(self._default_art_url)
        if pix is not None:
            target = QSize(self.episode_art.maximumWidth(), self.episode_art.maximumHeight())
            if target.width() <= 0 or target.height() <= 0:
                target = QSize(120, 120)
            self.episode_art.setPixmap(
                pix.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.episode_art.clear()

    def _on_generate_summary(self) -> None:
        idx = self.list.currentIndex()
        if not idx.isValid():
            return
        row = idx.row()
        if not (0 <= row < self.model.rowCount()):
            return
        ep = self.model.episode_at(row)
        if ep is None:
            return
        sub = getattr(self, "_current_sub", None)
        if sub is None or self._jobs is None:
            return
        key = self._feeds_meta.get_or_create_key(sub.name, sub.feed_url)
        pub_iso = ep.published.isoformat() if ep.published else None
        entry = self._episodes_index.find(
            key,
            getattr(ep, "guid", None),
            getattr(ep, "enclosure_url", None),
            pub_iso,
            ep.title,
        )
        if entry is None or entry.txt_path is None or entry.episode_dir is None:
            self.summary_header_label.setText("No transcript")
            self.summary_view.setPlainText(
                "Transcribe this episode first before generating a summary."
            )
            return
        try:
            job_id = self._jobs.enqueue_summarization(
                podcast=sub.name,
                title=ep.title,
                feed_url=sub.feed_url,
                guid=getattr(ep, "guid", None),
                enclosure_url=getattr(ep, "enclosure_url", None),
                published_date=pub_iso,
                txt_path=Path(entry.txt_path),
                episode_dir=Path(entry.episode_dir),
                key=key,
                force=True,
            )
            self._job_rows[job_id] = row
            self.summary_header_label.setText("Summarising…")
            self.summary_view.setPlainText("")
        except Exception as e:
            self.summary_header_label.setText("Error")
            self.summary_view.setPlainText(str(e))


__all__ = ["PodcastView"]
