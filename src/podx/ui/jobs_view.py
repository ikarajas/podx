from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QItemSelectionModel,
    QThread,
    QTimer,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPalette,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHeaderView,
    QLabel,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableView,
    QToolBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

from podx.services.jobs import Job, JobsService


EM_DASH = "\u2014"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _format_dt(value: Optional[str]) -> str:
    dt = _parse_iso(value)
    if dt is None:
        return EM_DASH
    try:
        return dt.strftime("%b %d, %Y %H:%M")
    except Exception:
        return dt.isoformat()


def _duration_label(job: Job) -> tuple[str, Optional[int]]:
    start = _parse_iso(job.started_at)
    finished = _parse_iso(job.finished_at)
    if start is None or finished is None:
        return EM_DASH, None
    delta = finished - start
    if delta.total_seconds() < 0:
        return EM_DASH, None
    seconds = int(delta.total_seconds())
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        label = f"{hours:d}h {minutes:02d}m {secs:02d}s"
    elif minutes:
        label = f"{minutes:d}m {secs:02d}s"
    else:
        label = f"{secs:d}s"
    return label, seconds


def _path_exists(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        return Path(value).exists()
    except Exception:
        return False


def _progress_label(job: Job) -> str:
    percent = getattr(job, "percent", None)
    if percent is None:
        return EM_DASH
    try:
        percent_value = int(percent)
    except Exception:
        return EM_DASH
    if job.status in {"queued", "failed", "canceled"} and percent_value <= 0:
        return EM_DASH
    return f"{max(0, percent_value)}%"


def _status_label(status: str) -> str:
    mapping = {
        "queued": "Queued",
        "running": "Running",
        "succeeded": "Succeeded",
        "failed": "Failed",
        "canceled": "Canceled",
    }
    return mapping.get(status.lower(), status.title())


def _status_color(palette: QPalette, status: str) -> QColor:
    base = {
        "queued": QColor(120, 120, 120),
        "running": QColor(220, 165, 40),
        "succeeded": QColor(60, 170, 85),
        "failed": QColor(210, 70, 70),
        "canceled": QColor(150, 95, 190),
    }
    color = base.get(status.lower())
    if color is None:
        return palette.color(QPalette.ColorRole.Text)
    return color


def _job_label(job: Job) -> str:
    emoji = {
        "transcribe": "📝",
        "summarize": "🧾",
    }.get(job.type.lower(), "")
    left = f"{job.type.title()} — {job.podcast or EM_DASH}"
    if emoji:
        return f"{emoji} {left}: {job.title}" if job.title else f"{emoji} {left}"
    return f"{left}: {job.title}" if job.title else left


class _JobTableModel(QAbstractTableModel):
    """Table model exposing jobs for the Jobs view with sortable columns."""

    model_reset = pyqtSignal()

    COLUMN_ORDER = [
        "job",
        "status",
        "progress",
        "created",
        "finished",
        "duration",
    ]

    HEADERS = {
        "job": "Job",
        "status": "Status",
        "progress": "Progress",
        "created": "Created",
        "finished": "Finished",
        "duration": "Duration",
    }

    def __init__(self) -> None:
        super().__init__()
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._sort_column: str = "created"
        self._sort_order: Qt.SortOrder = Qt.SortOrder.DescendingOrder

    # Qt model API -----------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt signature
        if parent.isValid():
            return 0
        return len(self._order)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self.COLUMN_ORDER)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal:
            return super().headerData(section, orientation, role)
        if role == Qt.ItemDataRole.DisplayRole:
            key = self._column_key(section)
            return self.HEADERS.get(key, "")
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        job = self._job_for_row(index.row())
        if job is None:
            return None
        column = self._column_key(index.column())
        if role == Qt.ItemDataRole.DisplayRole:
            if column == "job":
                return _job_label(job)
            if column == "status":
                return _status_label(job.status)
            if column == "progress":
                return _progress_label(job)
            if column == "created":
                return _format_dt(job.created_at)
            if column == "finished":
                return _format_dt(job.finished_at)
            if column == "duration":
                return _duration_label(job)[0]
        if role == Qt.ItemDataRole.TextAlignmentRole and column in {"progress", "duration", "created", "finished"}:
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        if role == Qt.ItemDataRole.UserRole:
            return job.id
        if role == Qt.ItemDataRole.UserRole + 1:
            return self._sort_value(job, column)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # noqa: N802
        base = super().flags(index)
        if not index.isValid():
            return base
        return base | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # noqa: N802
        key = self._column_key(column)
        self._sort_column = key
        self._sort_order = order
        changed = self._apply_sort()
        if changed:
            self.layoutChanged.emit()

    # Public helpers ---------------------------------------------------
    def update_job(self, job: Job) -> None:
        is_new = job.id not in self._jobs
        self._jobs[job.id] = job
        if is_new:
            self.beginInsertRows(QModelIndex(), len(self._order), len(self._order))
            self._order.append(job.id)
            self.endInsertRows()
        changed = self._apply_sort()
        if changed:
            self.layoutChanged.emit()
        else:
            row = self._order.index(job.id)
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right)
        if is_new:
            self.model_reset.emit()

    def jobs(self) -> Iterable[Job]:
        return (self._jobs[job_id] for job_id in self._order)

    def job_at(self, row: int) -> Optional[Job]:
        return self._job_for_row(row)

    # Internal helpers -------------------------------------------------
    def _column_key(self, column: int) -> str:
        try:
            return self.COLUMN_ORDER[column]
        except IndexError:
            return "job"

    def _job_for_row(self, row: int) -> Optional[Job]:
        if row < 0 or row >= len(self._order):
            return None
        job_id = self._order[row]
        return self._jobs.get(job_id)

    def _sort_value(self, job: Job, column: str):
        if column == "job":
            return _job_label(job).casefold()
        if column == "status":
            return _status_label(job.status)
        if column == "progress":
            return getattr(job, "percent", 0) or 0
        if column == "created":
            dt = _parse_iso(job.created_at)
            return dt or datetime.min
        if column == "finished":
            dt = _parse_iso(job.finished_at)
            return dt or datetime.min
        if column == "duration":
            return _duration_label(job)[1] or -1
        return 0

    def _apply_sort(self) -> bool:
        key = self._sort_column
        if key is None:
            return False
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        current = list(self._order)
        self._order.sort(key=lambda job_id: self._sort_value(self._jobs[job_id], key), reverse=reverse)
        return current != self._order


class _StatusDelegate(QStyledItemDelegate):
    """Custom delegate drawing colored status chips in the Jobs table."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: D401
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        status = opt.text
        color = _status_color(opt.palette, status.lower())
        metrics = QFontMetrics(opt.font)
        padding_x = metrics.horizontalAdvance(" ")
        padding_y = max(2, metrics.height() // 4)
        text_rect = opt.rect.adjusted(padding_x, padding_y, -padding_x, -padding_y)
        chip_width = metrics.horizontalAdvance(status) + padding_x * 2
        chip_rect = QRect(text_rect.left(), text_rect.top(), chip_width, text_rect.height())
        radius = chip_rect.height() // 2

        base_opt = QStyleOptionViewItem(opt)
        base_opt.text = ""
        base_opt.displayAlignment = Qt.AlignmentFlag.AlignCenter
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base_opt, painter, opt.widget)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bg = QColor(color)
        bg.setAlpha(90)
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(chip_rect, radius, radius)

        painter.setPen(color)
        painter.drawText(chip_rect, int(Qt.AlignmentFlag.AlignCenter), status)
        painter.restore()


class _JobDetailsPane(QWidget):
    """Pane summarising the currently selected job and exposing actions."""

    show_transcript_requested = pyqtSignal(Job)
    open_folder_requested = pyqtSignal(Job)
    copy_paths_requested = pyqtSignal(Job)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.title_label = QLabel("")
        title_font = QFont(self.title_label.font())
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 2)
        self.title_label.setFont(title_font)
        self.status_line = QLabel("")
        self.time_line = QLabel("")
        self.runtime_line = QLabel("")
        self.runtime_line.hide()

        layout.addWidget(self.title_label)
        layout.addWidget(self.status_line)
        layout.addWidget(self.time_line)
        layout.addWidget(self.runtime_line)

        self.outputs_label = QLabel("Outputs")
        outputs_font = QFont(self.outputs_label.font())
        outputs_font.setBold(True)
        self.outputs_label.setFont(outputs_font)
        self.outputs_label.hide()
        layout.addWidget(self.outputs_label)
        self.outputs = QLabel("")
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.outputs.setFont(mono_font)
        self.outputs.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.outputs)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.btn_show_transcript = QPushButton("Show Transcript")
        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_copy_paths = QPushButton("Copy Paths")
        button_row.addWidget(self.btn_show_transcript)
        button_row.addWidget(self.btn_open_folder)
        button_row.addWidget(self.btn_copy_paths)
        button_row.addStretch(1)

        layout.addLayout(button_row)
        layout.addStretch(1)

        self._job: Optional[Job] = None
        self.btn_show_transcript.clicked.connect(self._emit_show_transcript)
        self.btn_open_folder.clicked.connect(self._emit_open_folder)
        self.btn_copy_paths.clicked.connect(self._emit_copy_paths)
        self._set_enabled(False)

    def set_job(self, job: Optional[Job]) -> None:
        self._job = job
        if job is None:
            self.title_label.setText("Select a job to see details.")
            self.status_line.clear()
            self.time_line.clear()
            self.runtime_line.hide()
            self.outputs_label.hide()
            self.outputs.clear()
            self._set_enabled(False)
            return
        label = _job_label(job)
        self.title_label.setText(label)
        status = _status_label(job.status)
        duration_text, _ = _duration_label(job)
        progress = _progress_label(job)
        self.status_line.setText(f"{status} · {progress} · {duration_text}")

        created = _parse_iso(job.created_at)
        started = _parse_iso(job.started_at)
        finished = _parse_iso(job.finished_at)
        created_txt = created.strftime("%b %d %H:%M") if created else EM_DASH
        started_txt = started.strftime("%b %d %H:%M") if started else EM_DASH
        finished_txt = finished.strftime("%b %d %H:%M") if finished else EM_DASH
        self.time_line.setText(f"Created {created_txt} · Started {started_txt} · Finished {finished_txt}")

        runtime_bits: List[str] = []
        if getattr(job, "message", None):
            runtime_bits.append(job.message)
        if runtime_bits:
            self.runtime_line.setText(" · ".join(runtime_bits))
            self.runtime_line.show()
        else:
            self.runtime_line.hide()

        outputs: List[str] = []
        if job.vtt_path:
            label = f"Transcript (VTT): {job.vtt_path}"
            if not _path_exists(job.vtt_path):
                label += " (missing)"
            outputs.append(label)
        if job.txt_path:
            label = f"Transcript (TXT): {job.txt_path}"
            if not _path_exists(job.txt_path):
                label += " (missing)"
            outputs.append(label)
        if job.episode_dir:
            label = f"Episode Dir: {job.episode_dir}"
            if not _path_exists(job.episode_dir):
                label += " (missing)"
            outputs.append(label)
        if outputs:
            self.outputs_label.show()
            self.outputs.setText("\n".join(outputs))
        else:
            self.outputs_label.hide()
            self.outputs.clear()

        self._set_enabled(True)
        self._update_button_state(job)

    def _set_enabled(self, enabled: bool) -> None:
        for button in (self.btn_show_transcript, self.btn_open_folder, self.btn_copy_paths):
            button.setEnabled(enabled)

    def _update_button_state(self, job: Job) -> None:
        self.btn_show_transcript.setEnabled(bool(job.vtt_path or job.txt_path))
        self.btn_open_folder.setEnabled(bool(job.episode_dir or job.vtt_path or job.txt_path))
        self.btn_copy_paths.setEnabled(bool(job.vtt_path or job.txt_path or job.episode_dir))

    def _emit_show_transcript(self) -> None:
        if self._job:
            self.show_transcript_requested.emit(self._job)

    def _emit_open_folder(self) -> None:
        if self._job:
            self.open_folder_requested.emit(self._job)

    def _emit_copy_paths(self) -> None:
        if self._job:
            self.copy_paths_requested.emit(self._job)


@dataclass
class _LogLine:
    timestamp: Optional[str]
    level: Optional[str]
    text: str


class _LogsPane(QWidget):
    """Pane showing streaming logs for the selected job."""

    LEVELS = ["all", "info", "warning", "error"]
    MAX_LINES = 5000

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(16, 16))

        self.clear_action = QAction("Clear", self)
        self.copy_action = QAction("Copy All", self)
        self.toolbar.addAction(self.clear_action)
        self.toolbar.addAction(self.copy_action)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Info", "Warning", "Error"])
        self.toolbar.addWidget(self.filter_combo)

        layout.addWidget(self.toolbar)

        self.view = QPlainTextEdit()
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.view.setFont(mono_font)
        self.view.setReadOnly(True)
        self.view.setPlaceholderText("Log output will appear here when available…")
        layout.addWidget(self.view, 1)

        self._all_lines: List[_LogLine] = []
        self._selected_level = "all"
        self._auto_scroll = True
        self._job: Optional[Job] = None
        self._job_id: Optional[str] = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_logs)
        self.clear_action.triggered.connect(self._clear_view)
        self.copy_action.triggered.connect(self._copy_all)
        self.view.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)

    def set_job(self, job: Optional[Job]) -> None:
        job_id = job.id if job else None
        if job_id == self._job_id and job is not None:
            self._job = job
            self._poll_logs()
            return
        self._job = job
        self._job_id = job_id
        self._all_lines.clear()
        self.view.clear()
        if job is None:
            self._poll_timer.stop()
            self._set_filter_combo("All")
            return
        self._set_filter_combo("All")
        self._poll_timer.start()
        self._poll_logs(initial=True)

    def set_level_filter(self, level: str) -> None:
        level = level.lower()
        if level not in self.LEVELS:
            level = "all"
        self._selected_level = level
        self._render()

    # Slots ------------------------------------------------------------
    def _clear_view(self) -> None:
        self._all_lines.clear()
        self.view.clear()

    def _copy_all(self) -> None:
        text = self.view.toPlainText()
        QGuiApplication.clipboard().setText(text)

    def _on_scroll_changed(self, value: int) -> None:
        bar = self.view.verticalScrollBar()
        self._auto_scroll = value >= (bar.maximum() - 2)

    def _on_filter_changed(self, text: str) -> None:
        self.set_level_filter(text)

    def _set_filter_combo(self, label: str) -> None:
        block = self.filter_combo.blockSignals(True)
        try:
            index = self.filter_combo.findText(label, Qt.MatchFlag.MatchFixedString)
            if index >= 0:
                self.filter_combo.setCurrentIndex(index)
            else:
                self.filter_combo.setCurrentIndex(0)
        finally:
            self.filter_combo.blockSignals(block)
        self._selected_level = "all"

    # Log polling ------------------------------------------------------
    def _poll_logs(self, initial: bool = False) -> None:
        job = self._job
        if job is None:
            return
        log_paths: List[Path] = []
        for candidate in (job.txt_path, job.vtt_path, job.episode_dir):
            if not candidate:
                continue
            path = Path(candidate)
            if path.is_dir():
                logs_dir = path / "logs" / "transcribe.log"
                if logs_dir.exists():
                    log_paths.append(logs_dir)
            else:
                maybe = path.parent / "logs" / "transcribe.log"
                if maybe.exists():
                    log_paths.append(maybe)
        if not log_paths and job.message and initial:
            self._all_lines = [_LogLine(None, None, job.message)]
            self._render()
            return
        if not log_paths:
            return
        # Use the first available log path
        log_path = log_paths[0]
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        lines = content.splitlines()
        parsed = [self._parse_line(line) for line in lines]
        if len(parsed) > self.MAX_LINES:
            parsed = parsed[-self.MAX_LINES :]
        if len(parsed) == len(self._all_lines):
            return
        self._all_lines = parsed
        self._render()

    def _render(self) -> None:
        level = self._selected_level
        lines_to_show = []
        for line in self._all_lines:
            if level != "all" and (line.level or "info").lower() != level:
                continue
            bits = []
            if line.timestamp:
                bits.append(line.timestamp)
            if line.level:
                bits.append(line.level.upper())
            bits.append(line.text)
            lines_to_show.append(" ".join(bits))
        cursor_at_end = self._auto_scroll
        self.view.setPlainText("\n".join(lines_to_show))
        if cursor_at_end:
            cursor = self.view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.view.setTextCursor(cursor)

    @staticmethod
    def _parse_line(raw: str) -> _LogLine:
        parts = raw.split(" ", 2)
        if len(parts) >= 3 and parts[0].startswith("[") and parts[1].isupper():
            ts = parts[0].strip("[]")
            level = parts[1]
            rest = parts[2]
            return _LogLine(ts, level.lower(), rest)
        return _LogLine(None, None, raw)


class JobsView(QWidget):
    """Jobs dashboard showing queue, details, and logs."""

    _job_update_signal = pyqtSignal(object)

    def __init__(self, jobs: JobsService) -> None:
        super().__init__()
        self.jobs = jobs
        self._selected_job_id: Optional[str] = None
        self._jobs_model = _JobTableModel()
        self._job_update_signal.connect(self._apply_job_update)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        root.addWidget(splitter)

        # Jobs list -----------------------------------------------------
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(8, 8, 8, 8)
        self.table = QTableView()
        self.table.setModel(self._jobs_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, self._jobs_model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setItemDelegateForColumn(1, _StatusDelegate(self.table))
        self.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        top_layout.addWidget(self.table, 1)

        self.empty_state = QLabel("No jobs yet. Start a transcription from Subscriptions or Search.")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setContentsMargins(24, 24, 24, 24)
        self.empty_state.setWordWrap(True)
        top_layout.addWidget(self.empty_state)
        self.empty_state.hide()

        splitter.addWidget(top_container)

        # Details -------------------------------------------------------
        self.details = _JobDetailsPane()
        splitter.addWidget(self.details)

        # Logs ----------------------------------------------------------
        self.logs = _LogsPane()
        splitter.addWidget(self.logs)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 4)
        splitter.setSizes([280, 220, 260])

        # Wire signals --------------------------------------------------
        self.table.selectionModel().currentRowChanged.connect(self._on_selection_changed)
        self._jobs_model.model_reset.connect(self._refresh_empty_state)
        self.details.show_transcript_requested.connect(self._on_show_transcript)
        self.details.open_folder_requested.connect(self._on_open_folder)
        self.details.copy_paths_requested.connect(self._on_copy_paths)

        try:
            for job in self.jobs.list_jobs():
                self._jobs_model.update_job(job)
        except Exception:
            pass

        try:
            self.jobs.add_listener(self._on_job_update)
        except Exception:
            pass

        self._refresh_empty_state()

    # Slots ------------------------------------------------------------
    def _refresh_empty_state(self) -> None:
        has_rows = self._jobs_model.rowCount() > 0
        self.table.setVisible(has_rows)
        self.table.setEnabled(has_rows)
        self.empty_state.setVisible(not has_rows)
        if not has_rows:
            self.table.clearSelection()
            self.details.set_job(None)
            self.logs.set_job(None)
            self._selected_job_id = None
            return
        selection_model = self.table.selectionModel()
        if selection_model is not None and not selection_model.hasSelection():
            index = self._jobs_model.index(0, 0)
            if index.isValid():
                selection_model.select(
                    index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
                )
                self.table.setCurrentIndex(index)

    def _on_job_update(self, job: Job) -> None:
        if QThread.currentThread() is self.thread():
            self._apply_job_update(job)
        else:
            try:
                self._job_update_signal.emit(job)
            except Exception:
                pass

    def _apply_job_update(self, job: Job) -> None:
        previous_selection = self._selected_job_id
        self._jobs_model.update_job(job)
        if previous_selection:
            self._select_job(previous_selection)
        if self._selected_job_id == job.id:
            self.details.set_job(job)
            self.logs.set_job(job)
        self._refresh_empty_state()

    def _on_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        job = self._jobs_model.job_at(current.row()) if current.isValid() else None
        self._selected_job_id = job.id if job else None
        self.details.set_job(job)
        self.logs.set_job(job)

    def _select_job(self, job_id: str) -> None:
        for row in range(self._jobs_model.rowCount()):
            index = self._jobs_model.index(row, 0)
            if self._jobs_model.data(index, Qt.ItemDataRole.UserRole) == job_id:
                selection_model = self.table.selectionModel()
                selection_model.select(
                    index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
                )
                self.table.setCurrentIndex(index)
                self.table.scrollTo(index)
                break

    # Action handlers --------------------------------------------------
    def _on_show_transcript(self, job: Job) -> None:
        path = job.vtt_path or job.txt_path
        if not path:
            self._show_message("Transcript not available yet.")
            return
        file_path = Path(path)
        if not file_path.exists():
            self._show_message("Transcript file not found on disk.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path)))

    def _on_open_folder(self, job: Job) -> None:
        target = job.episode_dir
        if not target:
            path = job.vtt_path or job.txt_path
            if path:
                target = str(Path(path).parent)
        if not target:
            self._show_message("No output folder available yet.")
            return
        target_path = Path(target)
        if not target_path.exists():
            self._show_message("Output folder not found on disk.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path)))

    def _on_copy_paths(self, job: Job) -> None:
        paths: List[str] = []
        for candidate in [job.vtt_path, job.txt_path, job.episode_dir]:
            if not candidate:
                continue
            p = Path(candidate)
            if not p.exists():
                continue
            paths.append(str(p))
        if not paths:
            self._show_message("No output files available to copy.")
            return
        QGuiApplication.clipboard().setText("\n".join(paths))

    def _show_message(self, text: str) -> None:
        QToolTip.showText(QCursor.pos(), text, self)


__all__ = ["JobsView"]
