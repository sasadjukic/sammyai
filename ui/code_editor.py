"""The reusable SammyAI plain-text editor and line-number gutter."""

from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget


def _extract_color_from_stylesheet(
    selector: str,
    css_property: str,
) -> Optional[str]:
    """Extract a CSS color value from the application stylesheet."""
    try:
        application = QApplication.instance()
        stylesheet = application.styleSheet() if application is not None else ""
        pattern = rf"{selector}\s*\{{[^}}]*(?<!-){css_property}\s*:\s*([^;]+);"
        match = re.search(pattern, stylesheet or "")
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event) -> None:
        self._editor.lineNumberAreaPaintEvent(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

    def lineNumberAreaWidth(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return self.fontMetrics().horizontalAdvance("9") * digits + 12

    def updateLineNumberAreaWidth(self, _block_count: int) -> None:
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def _get_editor_background_color(self) -> QColor:
        color = _extract_color_from_stylesheet(
            "QPlainTextEdit",
            "background-color",
        )
        return QColor(color) if color else self.palette().color(QPalette.Base)

    def _get_editor_text_color(self) -> QColor:
        color = _extract_color_from_stylesheet("QPlainTextEdit", "color")
        return QColor(color) if color else self.palette().color(QPalette.Text)

    def updateLineNumberArea(self, rect, dy: int) -> None:
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(
                0,
                rect.y(),
                self.lineNumberArea.width(),
                rect.height(),
            )
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents = self.contentsRect()
        self.lineNumberArea.setGeometry(
            QRect(
                contents.left(),
                contents.top(),
                self.lineNumberAreaWidth(),
                contents.height(),
            )
        )

    def highlightCurrentLine(self) -> None:
        # Search and future decoration managers own extra selections.
        if not self.extraSelections():
            self.setExtraSelections([])

    def lineNumberAreaPaintEvent(self, event) -> None:
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), self._get_editor_background_color())
        painter.setFont(self.font())
        painter.setPen(self._get_editor_text_color())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())
        height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0,
                    top,
                    self.lineNumberArea.width() - 4,
                    height,
                    Qt.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

