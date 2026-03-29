from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QColor, QPen, QBrush
from .constants import TOP_MARGIN, MIN_TIMELINE_WIDTH

class HandleSignals(QObject):
    handleMoved = Signal(float)

class DraggableHandle(QGraphicsRectItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pin = parent
        self.signals = HandleSignals()
        self.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.SizeHorCursor)
        self._last_x = 0

    def mousePressEvent(self, event):
        self._last_x = event.scenePos().x()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.pin.timeline.window.play_controls.btn_save_video.setChecked(False)
        if self.pin.is_playing:
            self.pin.timeline.on_pause()
        self.pin.timeline.controls.set_playing(self.pin.is_playing)
        dx = event.scenePos().x() - self._last_x
        self._last_x = event.scenePos().x()
        self.signals.handleMoved.emit(dx)

    def paint(self, painter, option, widget):
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        radius = 3
        painter.drawRoundedRect(self.rect(), radius, radius)

class TimelineResizeHandle(QGraphicsRectItem):
    def __init__(self, timeline, width=5, height=35):
        super().__init__()
        self.timeline = timeline
        self.height = height
        self.setRect(0, 0, width, timeline.timeline_height)
        self.setBrush(QBrush(QColor("#595959")))
        self.setPen(QPen(Qt.NoPen))
        self.setCursor(Qt.SizeHorCursor)
        self.setZValue(200)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
        self.margin = 20
        self.setX(self.timeline.timeline_width)
        self._dragging = False

    def paint(self, painter, option, widget):
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        radius = 7
        painter.drawRoundedRect(self.rect(), radius, radius)

    def mousePressEvent(self, event):
        self.setX(self.timeline.timeline_width + self.margin)
        self._dragging = True
        self._start_x = event.scenePos().x()
        self._orig_width = self.timeline.timeline_width
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            dx = event.scenePos().x() - self._start_x
            new_width = max(max(self._orig_width + dx, MIN_TIMELINE_WIDTH), self.timeline.rightmost_clip)
            self.timeline.set_timeline_width(new_width)
            self.setX(new_width + self.margin)
            self.setY(0)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.timeline.derender_frames(self.timeline.timeline_width)
        if self.timeline.time_pin.frame_x > self.timeline.timeline_width:
            self.timeline.time_pin.set_frame(self.timeline.timeline_width)
        super().mouseReleaseEvent(event)

class TimePin(QGraphicsLineItem):
    def __init__(self, x, timeline):
        super().__init__(0, TOP_MARGIN, 0, timeline.get_timeline_height())
        self.timeline = timeline
        self.is_playing = False
        self.timeline_width = timeline.scene_obj.sceneRect().width()
        self.was_paused_automatically = False
        self.rendering_frames = []

        self.setPen(QPen(QColor("#FF3131"), 2))
        self.setZValue(100)

        self.frame_x = x
        self.setPos(x, TOP_MARGIN)

        self.handle = DraggableHandle(self)
        self.handle.setRect(-25, -17, 50, 17)
        self.handle.setBrush(QBrush(QColor("#FF3131")))
        self.handle.setPen(Qt.NoPen)

        self.handle.signals.handleMoved.connect(self.on_handle_moved)

        self.label = QGraphicsTextItem(str(x), self.handle)
        self.label.setDefaultTextColor(Qt.white)
        self.label.setPos(-15, -20)

    def set_frame(self, frame):
        self.handle.signals.handleMoved.emit(frame - self.frame_x)

    def on_handle_moved(self, dx):
        new_frame = self.frame_x + dx
        new_frame = max(0, min(new_frame, self.timeline_width))
        self.frame_x = new_frame
        self.setPos(new_frame, TOP_MARGIN)
        self.update_handle_position()
        self.label.setPlainText(str(int(new_frame)))

    def update_handle_position(self):
        half_w = self.handle.rect().width() / 2
        if self.frame_x < half_w:
            self.handle.setX(half_w - self.frame_x)
        elif self.frame_x > self.timeline_width - half_w:
            self.handle.setX(self.timeline_width - half_w - self.frame_x)
        else:
            self.handle.setX(0)
