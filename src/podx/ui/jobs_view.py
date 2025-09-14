from __future__ import annotations

from PyQt6.QtCore import Qt, QMetaObject
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
    QFormLayout,
    QPlainTextEdit,
)

from podx.services.jobs import JobsService, Job


class JobsView(QWidget):
    """Simple jobs list showing status and percent for background tasks."""

    def __init__(self, jobs: JobsService) -> None:
        super().__init__()
        self.jobs = jobs
        self.items: dict[str, QListWidgetItem] = {}
        self._cache: dict[str, Job] = {}
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)
        # Details panel
        self.details_panel = QWidget()
        form = QFormLayout(self.details_panel)
        self.lbl_title = QLabel("")
        self.lbl_status = QLabel("")
        self.lbl_percent = QLabel("")
        self.lbl_times = QLabel("")
        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        form.addRow("Title:", self.lbl_title)
        form.addRow("Status:", self.lbl_status)
        form.addRow("Progress:", self.lbl_percent)
        form.addRow("Times:", self.lbl_times)
        form.addRow("Result:", self.lbl_result)
        layout.addWidget(self.details_panel)
        self.txt_message = QPlainTextEdit()
        self.txt_message.setReadOnly(True)
        self.txt_message.setPlaceholderText("Job messages and errors will appear here…")
        layout.addWidget(self.txt_message, 1)
        # Subscribe to job updates
        try:
            self.jobs.add_listener(self._on_job_update)
        except Exception:
            pass
        # Selection changed updates details
        self.list.currentItemChanged.connect(self._on_selection_changed)

    def _on_job_update(self, job: Job) -> None:
        def apply():
            item = self.items.get(job.id)
            text = f"{job.type.title()} — {job.podcast}: {job.title}  •  {job.percent}%  •  {job.status}"
            if item is None:
                item = QListWidgetItem(text)
                self.items[job.id] = item
                item.setData(Qt.ItemDataRole.UserRole, job.id)
                self.list.addItem(item)
            else:
                item.setText(text)
            # Cache job
            self._cache[job.id] = job
            cur = self.list.currentItem()
            if cur is not None and cur.data(Qt.ItemDataRole.UserRole) == job.id:
                self._populate_details(job)
        try:
            QMetaObject.invokeMethod(self.list, apply, Qt.ConnectionType.QueuedConnection)
        except Exception:
            apply()

    def _on_selection_changed(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None = None) -> None:
        if current is None:
            self._clear_details()
            return
        job_id = current.data(Qt.ItemDataRole.UserRole)
        job = self._cache.get(job_id)
        if job is None:
            self._clear_details()
            return
        self._populate_details(job)

    def _populate_details(self, job: Job) -> None:
        self.lbl_title.setText(f"{job.podcast} — {job.title}")
        self.lbl_status.setText(job.status.title())
        self.lbl_percent.setText(f"{job.percent}%")
        parts = []
        if job.created_at:
            parts.append(f"Created: {job.created_at}")
        if job.started_at:
            parts.append(f"Started: {job.started_at}")
        if job.finished_at:
            parts.append(f"Finished: {job.finished_at}")
        self.lbl_times.setText("  |  ".join(parts))
        res = []
        if job.episode_dir:
            res.append(f"Dir: {job.episode_dir}")
        if job.vtt_path:
            res.append(f"VTT: {job.vtt_path}")
        if job.txt_path:
            res.append(f"TXT: {job.txt_path}")
        self.lbl_result.setText("\n".join(res) if res else "—")
        self.txt_message.setPlainText(job.message or "")

    def _clear_details(self) -> None:
        self.lbl_title.clear()
        self.lbl_status.clear()
        self.lbl_percent.clear()
        self.lbl_times.clear()
        self.lbl_result.clear()
        self.txt_message.clear()


__all__ = ["JobsView"]

