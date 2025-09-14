from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QFontMetrics
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem, QWidget, QToolTip

from .episodes_model import EpisodeListModel
from .utils import clean_html, format_episode_meta


class EpisodeDelegate(QStyledItemDelegate):
    """Render episodes similar to Apple Podcasts."""

    transcribeRequested = pyqtSignal(QModelIndex)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon_size = 24
        self._margin = 8
        self._item_height = 96
        style = QWidget().style()
        self._transcribe_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self._done_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        self._progress_icon = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self._failed_icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)

    # Painting
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, option.palette.highlight())
        # Text area (no per-item artwork for performance)
        text_left = rect.left() + self._margin
        text_width = rect.width() - (text_left - rect.left()) - self._icon_size - self._margin
        y = rect.top() + self._margin

        # Title
        title = clean_html(index.data(EpisodeListModel.TitleRole) or "")
        title_font = QFont(option.font)
        title_font.setBold(True)
        title_font.setPointSize(option.font.pointSize() + 2)
        painter.setFont(title_font)
        painter.setPen(option.palette.text().color())
        painter.drawText(QRect(text_left, y, text_width, 24), Qt.TextFlag.TextSingleLine, title)
        y += 24

        # Description
        desc = clean_html(index.data(EpisodeListModel.DescriptionRole) or "")
        desc_font = QFont(option.font)
        desc_font.setPointSize(option.font.pointSize() - 1)
        painter.setFont(desc_font)
        # Higher-contrast secondary text in dark/light and when selected
        base_sec = option.palette.highlightedText().color() if selected else option.palette.text().color()
        sec = QColor(base_sec)
        if not selected:
            sec.setAlpha(200)
        painter.setPen(sec)
        desc_height = 2 * painter.fontMetrics().lineSpacing()
        desc_rect = QRect(text_left, y, text_width, desc_height)
        painter.drawText(desc_rect, Qt.TextFlag.TextWordWrap, desc)
        y = desc_rect.bottom()

        # Meta line
        meta = format_episode_meta(
            index.data(EpisodeListModel.DateRole),
            index.data(EpisodeListModel.DurationRole),
        )
        meta_font = QFont(option.font)
        meta_font.setPointSize(option.font.pointSize() - 2)
        painter.setFont(meta_font)
        # Date/duration line: ensure strong contrast
        base_meta = option.palette.highlightedText().color() if selected else option.palette.text().color()
        meta_pen = QColor(base_meta)
        if not selected:
            meta_pen.setAlpha(220)
        painter.setPen(meta_pen)
        meta_height = painter.fontMetrics().lineSpacing()
        meta_rect = QRect(text_left, y + self._margin, text_width, meta_height)
        painter.drawText(meta_rect, Qt.TextFlag.TextSingleLine, meta)

        # Transcribe icon
        icon_rect = self._icon_rect(option)
        status = index.data(EpisodeListModel.StatusRole)
        if status == "transcribed" or index.data(EpisodeListModel.TranscribedRole):
            icon = self._done_icon
        elif status == "in_progress":
            icon = self._progress_icon
        elif status == "failed":
            icon = self._failed_icon
        else:
            icon = self._transcribe_icon
        icon.paint(painter, icon_rect)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        # Uniform, fixed height to skip per-item height calculations
        return QSize(-1, self._item_height)

    # Helpers
    def _icon_rect(self, option: QStyleOptionViewItem) -> QRect:
        rect = option.rect
        x = rect.right() - self._margin - self._icon_size
        y = rect.top() + (rect.height() - self._icon_size) // 2
        return QRect(x, y, self._icon_size, self._icon_size)

    def editorEvent(
        self,
        event: QEvent,
        model,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.MouseButtonRelease:
            me: QMouseEvent = event  # type: ignore[assignment]
            if me.button() == Qt.MouseButton.LeftButton and self._icon_rect(option).contains(me.pos()):
                # Ignore clicks while in progress
                status = index.data(EpisodeListModel.StatusRole)
                if status != "in_progress":
                    self.transcribeRequested.emit(index)
                return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):  # type: ignore[override]
        if event.type() == QEvent.Type.ToolTip:
            desc = clean_html(index.data(EpisodeListModel.DescriptionRole) or "")
            if desc:
                fm = QFontMetrics(option.font)
                max_w = max(300, int(view.viewport().width() * 0.6))
                text = self._wrap_text(desc, fm, max_w)
                QToolTip.showText(event.globalPos(), text, view)
                return True
        return super().helpEvent(event, view, option, index)

    def _wrap_text(self, text: str, fm: QFontMetrics, max_width: int) -> str:
        words = text.split()
        if not words:
            return ""
        lines: list[str] = []
        current = words[0]
        for w in words[1:]:
            test = current + " " + w
            if fm.horizontalAdvance(test) <= max_width:
                current = test
            else:
                lines.append(current)
                current = w
        lines.append(current)
        return "\n".join(lines)


__all__ = ["EpisodeDelegate"]

