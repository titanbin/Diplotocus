from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QColor, QDrag

class PaletteList(QListWidget):
    def mouseMoveEvent(self, event):
        item = self.currentItem()
        if not item:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(item.text())
        drag.setMimeData(mime)

        drag.exec(Qt.CopyAction)

class PaletteListItem(QListWidgetItem):
    def __init__(self, text, color="#333", parent=None):
        super().__init__(text, parent)
        self.setBackground(QColor(color))
        font = self.font()
        font.setPointSize(13)
        self.setFont(font)
