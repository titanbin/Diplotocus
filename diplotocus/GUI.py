import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QGraphicsView,QGraphicsTextItem,
    QGraphicsScene, QGraphicsRectItem, QHBoxLayout, QVBoxLayout, QGraphicsLineItem,
    QLabel, QSizePolicy,QSplitter, QPushButton, QDialog, QLineEdit, QFormLayout, QComboBox, QListWidgetItem
)
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QObject, QMimeData, QEvent, QTimer, Slot, QThread, QSize, QPoint
from PySide6.QtGui import QBrush, QColor, QPen, QPixmap, QDrag, QIcon, QKeySequence, QShortcut, QGuiApplication, QFontMetrics, QFont
from PySide6.QtTest import QTest

import queue,os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import easings

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

# -----------------------------
# Timeline Clip
# -----------------------------
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

class ElidedGraphicsTextItem(QGraphicsTextItem):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.parent = parent
        self.full_text = text
        self.max_width = 0
        self.setPlainText(text)

    def set_text(self, text):
        self.full_text = text
        self.set_max_width()

    def set_max_width(self):
        self.max_width = self.parent.rect().width() - 10
        self.update_elided()

    def update_elided(self):
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(
            self.full_text,
            Qt.ElideRight,
            int(self.max_width)
        )
        self.setPlainText(elided)

class TimelineClip(QGraphicsRectItem):
    def __init__(self, timeline, x, row, name, color):
        self.timeline = timeline
        self.plot_object = None
        super().__init__(0, 0, CLIP_WIDTH, self.timeline.row_height)
        self.just_spawned = True

        self.base_color = color#self.get_color_for_name(name)
        self.name = name

        self.setFlags(
            QGraphicsRectItem.ItemIsMovable |
            QGraphicsRectItem.ItemSendsGeometryChanges |
            QGraphicsRectItem.ItemIsSelectable
        )

        self.setAcceptHoverEvents(True)

        self.resize_left = False
        self.resize_right = False
        self.drag_start_pos = None
        self.orig_rect = None
        self.anim = None

        self.type_label = ElidedGraphicsTextItem(name, self)
        self.type_label.setDefaultTextColor(Qt.white)
        self.type_label.setPos(5, 5) 
        self.type_label.setTextWidth(CLIP_WIDTH - 10)
        self.type_label.setFlag(QGraphicsTextItem.ItemIsSelectable, False)
        self.type_label.setFlag(QGraphicsTextItem.ItemIsFocusable, False)

        self.obj_label = ElidedGraphicsTextItem('', self)
        self.obj_label.setDefaultTextColor(Qt.white)
        self.obj_label.setPos(5, 20)
        self.obj_label.setTextWidth(CLIP_WIDTH - 10)
        self.obj_label.setFlag(QGraphicsTextItem.ItemIsSelectable, False)
        self.obj_label.setFlag(QGraphicsTextItem.ItemIsFocusable, False)

        self.add_plot_object(name,x)

        self.update_labels()

        self.setPos(x, self.row_to_y(row))

        self.timeline.derender_frames(x)
        self.timeline.render_current_frame(x,x+CLIP_WIDTH)
        if self.timeline.timeline_width < x+CLIP_WIDTH:
            self.timeline.set_timeline_width(x+CLIP_WIDTH)
        if x+CLIP_WIDTH > self.timeline.rightmost_clip:
            self.timeline.rightmost_clip = x+CLIP_WIDTH

        self.open_settings()

    def update_labels(self):
        self.type_label.set_text(self.name)
        if self.plot_object is None:
            text = ''
        else:
            text = self.plot_object['name']
        self.obj_label.set_text(text)

    def add_plot_object(self,name,x):
        if self.plot_object is None:
            return
        if name == "Translate":
            self.plot_object['object'].translate((0,0),(1,1),duration=CLIP_WIDTH+1,delay=x)
        elif name == "Rotate":
            self.plot_object['object'].rotate(0,360,duration=CLIP_WIDTH+1,delay=x)
        elif name == "Scale":
            self.plot_object['object'].scale((1,1),(2,2),duration=CLIP_WIDTH+1,delay=x)
        self.anim = self.plot_object['object'].anims[-1]

    def get_color_for_name(self, name):
        if name == "Translate":
            return QColor("#4A90E2")
        elif name == "Rotate":
            return QColor("#50E3C2")
        elif name == "Scale":
            return QColor("#F5A623")
        else:
            return QColor("#999999")

    def mousePressEvent(self, event):
        x = event.pos().x()
        self.drag_start_pos = event.scenePos()
        self.orig_rect = self.rect()

        if x < EDGE_GRAB:
            self.resize_left = True
            self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        elif x > self.rect().width() - EDGE_GRAB:
            self.resize_right = True
            self.setFlag(QGraphicsRectItem.ItemIsMovable, False)
        else:
            self.setCursor(Qt.ClosedHandCursor)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resize_left or self.resize_right:
            delta = event.scenePos().x() - self.drag_start_pos.x()

            if self.resize_left:
                new_width = self.orig_rect.width() - delta
                if new_width >= MIN_CLIP_WIDTH:
                    if self.validate_resize(self.pos().x()+delta, new_width):
                        self.setRect(delta, 0, new_width, self.timeline.row_height)

            elif self.resize_right:
                new_width = self.orig_rect.width() + delta
                if new_width >= MIN_CLIP_WIDTH:
                    if self.validate_resize(self.pos().x(), new_width):
                        self.setRect(0, 0, new_width, self.timeline.row_height)

            if self.plot_object is not None:
                anim_i = self.plot_object['object'].anims.index(self.anim)
                self.plot_object['object'].anims[anim_i]['duration'] = new_width+1
            self.timeline.derender_frames(self.pos().x())
            
            self.type_label.set_max_width()
            self.type_label.setPos(self.rect().x()+5,self.type_label.pos().y())
            self.obj_label.set_max_width()
            self.obj_label.setPos(self.rect().x()+5,self.obj_label.pos().y())
        else:
            super().mouseMoveEvent(event)

    def row_to_y(self, row):
        return self.timeline.top_margin + row * self.timeline.row_height

    def y_to_row(self, y):
        return int(round((y - self.timeline.top_margin) / self.timeline.row_height))
    
    def hoverMoveEvent(self, event):
        x = event.pos().x()
        if x < EDGE_GRAB or x > self.rect().width() - EDGE_GRAB:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemPositionChange:
            if self.just_spawned:
                self.just_spawned = False
                return super().itemChange(change, value)
            new_pos = value

            x = max(
                LEFT_MARGIN,
                min(new_pos.x(), self.timeline.timeline_width - self.rect().width())
            )

            row = max(0, min(NUM_ROWS - 1, self.y_to_row(new_pos.y())))
            y = self.row_to_y(row)

            proposed_pos = QPointF(x, y)

            test_rect = QRectF(
                x,y,
                self.rect().width(), self.rect().height()
            )
            if self.timeline.check_overlap(self, test_rect):
                return self.pos()

            if self.plot_object is not None:
                anim_i = self.plot_object['object'].anims.index(self.anim)
                self.plot_object['object'].anims[anim_i]['delay'] = proposed_pos.x()
            frames_to_derender = min(self.pos().x(),proposed_pos.x())
            self.timeline.derender_frames(frames_to_derender)
            return proposed_pos

        return super().itemChange(change, value)
    
    def paint(self, painter, option, widget):
        color = QColor(self.base_color)
        if self.isSelected():
            color = color.darker(150)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())
    
    def mouseReleaseEvent(self, event):
        self.resize_left = False
        self.resize_right = False
        self.setCursor(Qt.OpenHandCursor)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        if self.rect().x() != 0:
            self.setPos(self.pos().x() + self.rect().x(),self.pos().y())
            self.setRect(0,0,self.rect().width(),self.rect().height())
            self.type_label.setPos(self.rect().x()+5,self.type_label.pos().y())
            self.obj_label.setPos(self.rect().x()+5,self.obj_label.pos().y())
        
        self.timeline.render_current_frame(self.pos().x(),self.pos().x()+self.rect().width())
        super().mouseReleaseEvent(event)

    def validate_resize(self, new_x, new_width):
        if new_x < 0 or new_x + new_width > self.timeline.timeline_width:
            return False
        return not self.timeline.check_overlap(
            self,
            QRectF(new_x, self.pos().y(), new_width, self.timeline.row_height)
        )
    
    def mouseDoubleClickEvent(self, event):
        self.open_settings()
        event.accept()

    def open_settings(self):
        dialog = ClipSettingsDialog(self)
        dialog.exec()

class ClipSettingsDialog(QDialog):
    def __init__(self, clip, parent=None):
        super().__init__(parent)
        self.clip = clip

        self.main_layout = QVBoxLayout(self)

        self.make_layout(self.clip.name)

        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        self.main_layout.addWidget(btn)

    def accept(self):
        to_derender = False

        obj_i = self.plot_object.currentIndex()
        if obj_i == 0:
            new_plot_object = None
        else:
            new_plot_object = self.clip.timeline.window.GUI.plot_objects[obj_i-1]
        
        if new_plot_object != self.clip.plot_object:
            self.clip.timeline.derender_frames(0)
            was_none = self.clip.plot_object is None
            if was_none == False or new_plot_object is None:
                self.clip.plot_object['object'].anims.remove(self.clip.anim)
            if was_none and new_plot_object is not None:
                new_plot_object['object'].clean(new_plot_object['object'].x_min)
            self.clip.plot_object = new_plot_object
            if was_none:
                self.clip.add_plot_object(self.clip.name,self.clip.pos().x())
            elif self.clip.plot_object is not None:
                self.clip.plot_object['object'].anims.append(self.clip.anim)
            if self.clip.plot_object is None:
                self.clip.anim = None
        
        new_easing = getattr(sys.modules['easings'], self.easing.currentText())()
        new_name = new_easing.__class__.__name__
        if self.clip.anim is not None:
            old_name = self.clip.anim['easing'].__class__.__name__
            if new_name != old_name:
                self.clip.anim['easing'] = new_easing
                to_derender = True

        if self.clip.plot_object is not None:
            if self.clip.name == 'Translate':
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anim)
                prop = self.clip.plot_object['object'].anims[anim_i]

                start_x,start_y,end_x,end_y = self.sanitize_input(
                    [self.start_x,self.start_y,self.end_x,self.end_y],
                    lambda x:float(x),
                    [0,0,1,1]   
                )

                if prop['start'][0] != start_x or prop['start'][1] != start_y:
                    to_derender = True
                    prop['start'] = (start_x,start_y)
                if prop['end'][0] != end_x or prop['end'][1] != end_y:
                    to_derender = True
                    prop['end'] = (end_x,end_y)
            elif self.clip.name == 'Translate':
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anim)
                prop = self.clip.plot_object['object'].anims[anim_i]

                start,end = self.sanitize_input(
                    [self.start_x,self.end_x],
                    lambda x:float(x),
                    [0,360]   
                )

                if prop['start'] != start:
                    to_derender = True
                    prop['start'] = start
                if prop['end'] != end:
                    to_derender = True
                    prop['end'] = end
            elif self.clip.name == 'Scale':
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anim)
                prop = self.clip.plot_object['object'].anims[anim_i]

                start_x,start_y,end_x,end_y = self.sanitize_input(
                    [self.start_x,self.start_y,self.end_x,self.end_y],
                    lambda x:float(x),
                    [1,1,2,2]
                )

                if prop['start'][0] != start_x or prop['start'][1] != start_y:
                    to_derender = True
                    prop['start'] = (start_x,start_y)
                if prop['end'][0] != end_x or prop['end'][1] != end_y:
                    to_derender = True
                    prop['end'] = (end_x,end_y)

        self.clip.update_labels()
        
        if to_derender:
            self.clip.timeline.derender_frames(self.clip.pos().x())
        self.clip.timeline.window.preview.on_pin_moved()
        super().accept()

    def sanitize_input(self,inputs,func,defaults):
        sanitized_inputs = []
        for input,default in zip(inputs,defaults):
            try:
                sanitized_inputs.append(func(input.text()))
            except:
                sanitized_inputs.append(default)
        return sanitized_inputs

    def make_layout(self,type):
        self.setWindowTitle(type + " Settings")

        form = QFormLayout()

        if type == 'Translate':
            if self.clip.plot_object is not None:
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anim)
                prop = self.clip.plot_object['object'].anims[anim_i]
                start_x = prop['start'][0]
                start_y = prop['start'][1]
                end_x = prop['end'][0]
                end_y = prop['end'][1]
            else:
                start_x,start_y,end_x,end_y = 0,0,1,1
            self.start_x = QLineEdit()
            self.start_x.setText(str(start_x))
            form.addRow("Start X", self.start_x)
            self.start_y = QLineEdit()
            self.start_y.setText(str(start_y))
            form.addRow("Start Y", self.start_y)
            self.end_x = QLineEdit()
            self.end_x.setText(str(end_x))
            form.addRow("End X", self.end_x)
            self.end_y = QLineEdit()
            self.end_y.setText(str(end_y))
            form.addRow("End Y", self.end_y)
        elif type == 'Rotate':
            if self.clip.plot_object is not None:
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anim)
                prop = self.clip.plot_object['object'].anims[anim_i]
                start = prop['start']
                end = prop['end']
            else:
                start,end = 0,360
            
            self.start_x = QLineEdit()
            self.start_x.setText(str(start))
            form.addRow("Start angle (°)", self.start_x)
            self.end_x = QLineEdit()
            self.end_x.setText(str(end))
            form.addRow("End angle (°)", self.end_x)
        elif type == 'Scale':
            if self.clip.plot_object is not None:
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anim)
                prop = self.clip.plot_object['object'].anims[anim_i]
                start_x = prop['start'][0]
                start_y = prop['start'][1]
                end_x = prop['end'][0]
                end_y = prop['end'][1]
            else:
                start_x,start_y,end_x,end_y = 1,1,2,2
            self.start_x = QLineEdit()
            self.start_x.setText(str(start_x))
            form.addRow("Start scale X", self.start_x)
            self.start_y = QLineEdit()
            self.start_y.setText(str(start_y))
            form.addRow("Start scale Y", self.start_y)
            self.end_x = QLineEdit()
            self.end_x.setText(str(end_x))
            form.addRow("End scale X", self.end_x)
            self.end_y = QLineEdit()
            self.end_y.setText(str(end_y))
            form.addRow("End scale Y", self.end_y)

        self.easing = QComboBox()
        self.easing.addItems(easings.available_easings)

        easing = None
        if self.clip.anim is not None:
            easing = self.clip.anim['easing']
        if easing is None:
            easing = 'easeLinear'
        else:
            easing = easing.__class__.__name__
        index = self.easing.findText(easing)
        if index >= 0:
            self.easing.setCurrentIndex(index)

        form.addRow('Easing',self.easing)

        self.plot_object = QComboBox()
        self.plot_object.addItem('None')
        for obj in self.clip.timeline.window.GUI.plot_objects:
            self.plot_object.addItem(obj['name'])
        if self.clip.plot_object is not None:
            index = self.plot_object.findText(self.clip.plot_object['name'])
        else:
            index = 0
        
        if index >= 0:
            self.plot_object.setCurrentIndex(index)

        form.addRow('Object',self.plot_object)

        self.main_layout.addLayout(form)

class TimePinSignal(QObject):
    pinMoved = Signal(str)

class TimePin(QGraphicsLineItem):
    def __init__(self, x, timeline):
        super().__init__(0, TOP_MARGIN, 0, timeline.get_timeline_height())
        self.timeline = timeline
        self.is_playing = False
        self.timeline_width = timeline.scene_obj.sceneRect().width()
        self.was_paused_automatically = False
        self.rendering_frames = []

        self.setPen(QPen(QColor("#FF0000"), 2))
        self.setZValue(100)

        self.frame_x = x
        self.setPos(x, TOP_MARGIN)

        self.handle = DraggableHandle(self)
        self.handle.setRect(-25, -15, 50, 15)
        self.handle.setBrush(QBrush(QColor("#FF0000")))
        self.handle.setPen(Qt.NoPen)

        self.handle.signals.handleMoved.connect(self.on_handle_moved)

        self.label = QGraphicsTextItem(str(x), self.handle)
        self.label.setDefaultTextColor(Qt.white)
        self.label.setPos(-15, -20)

    def set_frame(self,frame):
        self.handle.signals.handleMoved.emit(frame-self.frame_x)

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

# -------------------------------
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

# -----------------------------
# Timeline View
# -----------------------------
class TimelineResizeHandle(QGraphicsRectItem):
    def __init__(self, timeline, width=4):
        super().__init__()
        self.timeline = timeline
        self.setRect(0, 0, width, timeline.timeline_height)
        self.setBrush(QBrush(QColor("#888888")))
        self.setPen(QPen(Qt.NoPen))
        self.setCursor(Qt.SizeHorCursor)
        self.setZValue(200)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, False)
        self.margin = 20
        self.setX(self.timeline.timeline_width)
        self._dragging = False

    def mousePressEvent(self, event):
        self.setX(self.timeline.timeline_width + self.margin)
        self._dragging = True
        self._start_x = event.scenePos().x()
        self._orig_width = self.timeline.timeline_width
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            dx = event.scenePos().x() - self._start_x
            new_width = max(max(self._orig_width + dx, MIN_TIMELINE_WIDTH),self.timeline.rightmost_clip)
            self.timeline.set_timeline_width(new_width)
            self.setX(new_width + self.margin)
            self.setY(0)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.timeline.derender_frames(self.timeline.timeline_width)
        if self.timeline.time_pin.frame_x > self.timeline.timeline_width:
            self.timeline.time_pin.set_frame(self.timeline.timeline_width)
        super().mouseReleaseEvent(event)

class TimelineView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.top_margin = TOP_MARGIN
        self.bottom_margin = BOTTOM_MARGIN
        self.num_rows = NUM_ROWS
        self.row_height = 60
        self.timeline_height = self.get_timeline_height()
        self.timeline_width = TIMELINE_WIDTH
        self.loop = False

        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.scene_obj.setSceneRect(0, 0, self.timeline_width, self.timeline_height)

        self.time_pin = TimePin(0, self)
        self.scene_obj.addItem(self.time_pin)
        self.time_pin.set_frame(0)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(1000 // (30*3))
        self.play_timer.timeout.connect(self.advance_frame)

        self.rendered_frames = []
        self.rendered_rects = []
        
        self.background_rect = self.scene_obj.addRect(
            self.scene_obj.sceneRect(),
            pen=QPen(Qt.NoPen),
            #brush=QBrush(QColor("#0EA35B"))
        )
        self.resize_handle = TimelineResizeHandle(self)
        self.scene_obj.addItem(self.resize_handle)
        self.update_resize_handle()

        self.row_lines = []
        self.draw_row_lines()

        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.horizontalScrollBar().installEventFilter(self)
        self.setFocusPolicy(Qt.StrongFocus)

        self.rightmost_clip = 0

    def update_resize_handle(self):
        rect = self.background_rect.rect()
        self.resize_handle.setX(rect.right() + self.resize_handle.margin)
        self.resize_handle.setY(0)

    def is_frame_rendered(self, frame: int) -> bool:
        return frame in self.rendered_frames

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Backspace:
            x_min = self.timeline_width
            x_max = 0
            for item in self.scene_obj.selectedItems():
                if isinstance(item, TimelineClip):
                    if item.pos().x() < x_min:
                        x_min = item.pos().x()
                    if item.pos().x() + item.rect().width() > x_max:
                        x_max = item.pos().x() + item.rect().width()
                    if item.plot_object is not None:
                        item.plot_object['object'].anims.remove(item.anim)
                    self.scene_obj.removeItem(item)
                    del item
            event.accept()

            self.derender_frames(x_min)
            
            self.render_current_frame(x_min,x_max)
            return

        super().keyPressEvent(event)

    def render_current_frame(self,xmin=-1,xmax=None):
        if xmax is None:
            xmax = self.timeline_width+2
        current_frame = self.time_pin.frame_x
        if xmin <= current_frame <= xmax:
            if current_frame in self.rendered_frames:
                self.rendered_frames.remove(current_frame)
            self.window.preview.on_pin_moved()

    def add_rendered_frame(self,_,frame):
        if frame not in self.rendered_frames:
            self.rendered_frames.append(frame)
            
            rect_exists = any(rect.rect().x() == frame for rect in self.rendered_rects)
            if not rect_exists:
                self.rendered_rects.append(self.scene_obj.addRect(
                    frame, 0, 1, TOP_MARGIN,
                    pen=QPen(Qt.NoPen),
                    brush=QBrush(QColor("#0EA35B"))
                ))

    def derender_frames(self,frame):
        new_rendered_frames = []
        new_rendered_rects = []
        for rendered_frame,rendered_rect in zip(self.rendered_frames,self.rendered_rects):
            if rendered_frame < frame:
                new_rendered_frames.append(rendered_frame)
                new_rendered_rects.append(rendered_rect)
            else:
                self.scene_obj.removeItem(rendered_rect)
        
        self.window.preview.worker.remove_frames_greater_than(frame)

        self.rendered_frames = new_rendered_frames
        self.rendered_rects = new_rendered_rects

    def get_timeline_height(self):
        return max(self.height(), self.num_rows * 60) - self.top_margin - 20

    def set_timeline_width(self, width):
        self.timeline_width = width
        self.timeline_height = self.get_timeline_height()
        self.scene_obj.setSceneRect(0, 0, width + 50, self.timeline_height+self.top_margin)
        self.background_rect.setRect(self.scene_obj.sceneRect())
        self.update_resize_handle()
        self.draw_row_lines()
        # Update clips and pin positions as needed
        for item in self.scene_obj.items():
            if isinstance(item, TimelineClip):
                row = item.y_to_row(item.pos().y())
                item.setRect(0, 0, item.rect().width(), self.row_height)
                item.setPos(item.pos().x(), item.row_to_y(row))
        self.time_pin.timeline_width = width
    
    def resizeEvent(self, event):
        self.update_resize_handle()
        self.timeline_height = self.get_timeline_height()
        self.row_height = self.timeline_height / self.num_rows
        self.scene_obj.setSceneRect(0, 0, self.timeline_width, self.timeline_height + self.top_margin)
        self.background_rect.setRect(self.scene_obj.sceneRect())
        self.draw_row_lines() 
        
        self.time_pin.timeline_height = self.timeline_height
        self.time_pin.setLine(0, 0, 0, self.timeline_height)

        for item in self.scene_obj.items():
            if isinstance(item, TimelineClip):
                row = item.y_to_row(item.pos().y())
                item.setRect(0,0,item.rect().width(),self.row_height)
                item.setPos(item.pos().x(), item.row_to_y(row))
        super().resizeEvent(event)

    def draw_row_lines(self):
        if len(self.row_lines) == 0:
            self.create_row_lines()
        else:
            for i,rect in enumerate(self.row_lines):
                y1 = self.top_margin + i * self.row_height
                y2 = self.top_margin + (i+1) * self.row_height
                rect.setPos(rect.x(),y1)
                rect.setRect(0,0,self.timeline_width,y2-y1)
        
    def create_row_lines(self):
        for i in range(self.num_rows):
            y1 = self.top_margin + i * self.row_height
            y2 = self.top_margin + (i+1) * self.row_height
            rect = self.scene_obj.addRect(
                0,y1,self.timeline_width,y2,
                brush=QBrush(QColor("#2B2B2B"))
            )
            self.row_lines.append(rect)

    def advance_frame(self):
        if self.window.preview.worker.queue.empty() == False and self.is_frame_rendered(self.time_pin.frame_x) == False:
            return

        self.window.preview.on_pin_moved()
        new_frame = (self.time_pin.frame_x + 1)
        self.time_pin.set_frame(new_frame)
        if new_frame == self.timeline_width:
            if self.loop and self.window.play_controls.btn_save_video.isChecked() == False:
                self.time_pin.set_frame(0)
            else:
                self.time_pin.is_playing = False
                self.play_timer.stop()
                self.controls.set_playing(False)
                if self.window.play_controls.btn_save_video.isChecked():
                    self.window.play_controls.btn_save_video.setChecked(False)
                    self.window.GUI.seq.x = self.timeline_width+1
                    self.window.GUI.seq.save_video(clean=False)

    def on_loop(self):
        self.loop = not self.loop

    def on_play(self):
        self.window.preview.on_pin_moved()
        self.time_pin.was_paused_automatically = False
        self.time_pin.is_playing = True
        self.time_pin.timeline.window.play_controls.set_playing(True)
        if self.time_pin.frame_x == self.timeline_width:
            self.time_pin.set_frame(0)
        if not self.play_timer.isActive():
            self.play_timer.start()

    def on_pause(self):
        self.window.play_controls.btn_save_video.setChecked(False)
        self.time_pin.is_playing = False
        self.time_pin.was_paused_automatically = False
        self.time_pin.timeline.window.play_controls.set_playing(False)
        self.play_timer.stop()

    def on_step_forward(self):
        self.window.play_controls.btn_save_video.setChecked(False)
        self.time_pin.was_paused_automatically = False
        self.time_pin.set_frame(self.time_pin.frame_x+1)
        if self.time_pin.is_playing:
            self.time_pin.is_playing = False
            self.play_timer.stop()
            self.controls.set_playing(False)

    def on_step_backward(self):
        self.window.play_controls.btn_save_video.setChecked(False)
        self.time_pin.was_paused_automatically = False
        self.time_pin.set_frame(self.time_pin.frame_x-1)
        if self.time_pin.is_playing:
            self.time_pin.is_playing = False
            self.play_timer.stop()
            self.controls.set_playing(False)

    def on_to_start(self):
        self.window.play_controls.btn_save_video.setChecked(False)
        self.time_pin.was_paused_automatically = False
        self.time_pin.set_frame(0)
        if self.time_pin.is_playing:
            self.play_timer.stop()
            self.controls.set_playing(False)

    def on_to_end(self):
        self.window.play_controls.btn_save_video.setChecked(False)
        self.time_pin.was_paused_automatically = False
        self.time_pin.set_frame(self.timeline_width)
        if self.time_pin.is_playing:
            self.time_pin.is_playing = False
            self.play_timer.stop()
            self.controls.set_playing(False)

    def save_video(self):
        if self.window.play_controls.btn_save_video.isChecked():
            self.time_pin.set_frame(0)
            self.on_play()

    def eventFilter(self, obj, event):
        if obj is self.horizontalScrollBar():
            if event.type() == QEvent.Hide:
                self.horizontalScrollBar().show()
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        row = max(0, min(self.num_rows - 1, int((scene_pos.y() - self.top_margin) / self.row_height)))
        x = max(LEFT_MARGIN, min(scene_pos.x() - CLIP_WIDTH/2, self.timeline_width))
        clip_name = event.mimeData().text()
        color = '#999999'
        for i in range(self.window.list_widget.count()):
            item = self.window.list_widget.item(i)
            if item.text() == clip_name:
                color = item.background().color().name()
                break

        clip = TimelineClip(self, x, row, clip_name, color)
        rect = QRectF(
            x, clip.row_to_y(row),
            clip.rect().width(), clip.rect().height()
        )
        if not self.check_overlap(clip, rect):
            self.scene_obj.addItem(clip)
        event.acceptProposedAction()

    def check_overlap(self, moving_clip, test_rect):
        for item in self.scene_obj.items():
            if item is moving_clip:
                continue
            if isinstance(item, TimelineClip):
                other_rect = QRectF(
                    item.pos().x(), item.pos().y()+1,
                    item.rect().width(), item.rect().height()-2
                )
                if test_rect.intersects(other_rect):
                    return True
        return False

class PreviewWorker(QObject):
    imageReady = Signal(str, int)
    renderImage = Signal(int)
    beforeImageReady = Signal(bool, int)

    def __init__(self, base_path, window):
        super().__init__()
        self.window = window
        self.base_path = base_path
        self.queue = queue.Queue()
        self._running = True
        self._processing = False

    @Slot(int)
    def enqueue(self, frame):
        self.queue.put(frame)
        self.process_next_frame()

    def stop(self):
        self._running = False
        self.queue.put(None)

    def remove_frames_greater_than(self, x):
        kept = []
        try:
            while True:
                frame = self.queue.get_nowait()
                if frame <= x:
                    kept.append(frame)
                self.queue.task_done()
        except queue.Empty:
            pass
        for frame in kept:
            self.queue.put(frame)

    def process_next_frame(self):
        if self._processing or not self._running:
            return
        if self.queue.empty():
            return

        self._processing = True
        frame = self.queue.get()
        if frame is None:
            self._processing = False
            return

        path = self.base_path.format(frame)
        was_playing = self.window.timeline.time_pin.is_playing
        if frame not in self.window.timeline.time_pin.rendering_frames and frame not in self.window.timeline.rendered_frames:
            self.window.timeline.time_pin.rendering_frames.append(frame)
            if was_playing:
                self.beforeImageReady.emit(False, frame)

            self.renderImage.emit(frame)

            self.window.timeline.time_pin.rendering_frames.remove(frame)
            if was_playing:
                if self.window.timeline.time_pin.was_paused_automatically:
                    self.beforeImageReady.emit(True, frame)

        self.imageReady.emit(path, frame)
        self._processing = False

        QTimer.singleShot(0, self.process_next_frame)

class PreviewWidget(QWidget):
    def __init__(self, base_path, parent=None):
        super().__init__(parent)
        self.window_widget = parent

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.base_path = base_path
        self.pixmap = None

        self.thread = QThread(self)
        self.worker = PreviewWorker(base_path,self.window_widget)
        self.worker.moveToThread(self.thread)

        self.worker.renderImage.connect(self.render_frame)
        self.worker.imageReady.connect(self.on_image_ready)
        self.worker.beforeImageReady.connect(self.before_image_ready)

        self.thread.start()

    def render_frame(self, frame):
        self.window_widget.GUI.seq.clean_all()
        objs = [el['object'] for el in self.window_widget.GUI.plot_objects]
        self.window_widget.GUI.seq.plot(objs,x=frame)

    def on_pin_moved(self, _=None):
        frame = int(self.timeline.time_pin.frame_x)
        if frame not in self.timeline.rendered_frames:
            self.worker.enqueue(frame)
        else:
            path = self.base_path.format(frame)
            self.on_image_ready(path,frame)

    def before_image_ready(self,state,frame):
        current_frame = int(self.timeline.time_pin.frame_x)
        
        if frame != current_frame:
            return
        old_state = self.window_widget.timeline.time_pin.is_playing
    
        if state and self.window_widget.timeline.time_pin.was_paused_automatically:
            self.window_widget.timeline.time_pin.is_playing = True
            self.window_widget.timeline.play_timer.start()
        elif old_state:
            self.window_widget.timeline.time_pin.is_playing = False
            self.window_widget.timeline.time_pin.was_paused_automatically = True
            self.window_widget.timeline.play_timer.stop()

    def on_image_ready(self, path, frame):
        if frame != int(self.timeline.time_pin.frame_x):
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return

        self.pixmap = pixmap
        self.update_scaled_pixmap()

    def closeEvent(self, event):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
        super().closeEvent(event)

    def load_image(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self.pixmap = pixmap
        self.update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.label.setGeometry(0, 0, self.width(), self.height())
        self.update_scaled_pixmap()

    def update_scaled_pixmap(self):
        if self.pixmap:
            scaled = self.pixmap.scaled(
                self.width(),
                self.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.label.setPixmap(scaled)

class PlayControls(QWidget):
    playPressed = Signal()
    pausePressed = Signal()
    stepForward = Signal()
    stepBackward = Signal()
    toStart = Signal()
    toEnd = Signal()
    loop = Signal()
    saveVideo = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.is_playing = False

        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.btn_start = QPushButton("⏮")
        self.btn_start.setToolTip("Go to start")
        self.btn_start.clicked.connect(self.toStart.emit)

        self.btn_end = QPushButton("⏭")
        self.btn_end.setToolTip("Go to end")
        self.btn_end.clicked.connect(self.toEnd.emit)

        self.btn_back = QPushButton('⇤')
        font = self.btn_back.font()
        font.setPointSize(16)
        self.btn_back.setFont(font)
        self.btn_back.setToolTip("Previous frame")
        self.btn_back.clicked.connect(self.stepBackward.emit)

        self.btn_play = QPushButton("▶")
        self.btn_play.setToolTip("Play / Pause")
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_forward = QPushButton("⇥")
        font = self.btn_forward.font()
        font.setPointSize(16)
        self.btn_forward.setFont(font)
        self.btn_forward.setToolTip("Next frame")
        self.btn_forward.clicked.connect(self.stepForward.emit)

        self.btn_loop = QPushButton("⟳")
        self.btn_loop.setCheckable(True)
        font = self.btn_loop.font()
        font.setPointSize(21)
        self.btn_loop.setFont(font)
        self.btn_loop.setStyleSheet("qproperty-alignment: AlignCenter;")
        self.btn_loop.setStyleSheet("""
            QPushButton {
                padding-top: 0px;
                padding-bottom: 4px;
            }
        """)
        self.btn_loop.setToolTip("Loop video")
        self.btn_loop.clicked.connect(self.loop.emit)

        self.btn_save_video = QPushButton("⏺")
        self.btn_save_video.setCheckable(True)
        self.btn_save_video.setStyleSheet("QPushButton { color: red; }")
        self.btn_save_video.setToolTip("Save video")
        self.btn_save_video.clicked.connect(self.saveVideo.emit)

        size = 36
        for btn in (self.btn_start, self.btn_back, self.btn_play, self.btn_forward, self.btn_end, self.btn_loop, self.btn_save_video):
            btn.setFixedSize(size, size)
            btn.setFocusPolicy(Qt.NoFocus)

        layout.addStretch(1)
        
        spacer = QWidget()
        spacer.setFixedWidth(self.btn_back.width()*3)
        layout.addWidget(spacer)
        
        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_back)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_forward)
        layout.addWidget(self.btn_end)
        layout.addWidget(self.btn_loop)
        
        spacer = QWidget()
        spacer.setFixedWidth(self.btn_back.width())
        layout.addWidget(spacer)

        layout.addWidget(self.btn_save_video)

        layout.addStretch(1)

    def toggle_play(self):
        self.is_playing = not self.is_playing

        if self.is_playing:
            self.playPressed.emit()
        else:
            self.pausePressed.emit()

    def set_playing(self, playing):
        self.is_playing = playing
        self.btn_play.setText("⏸" if playing else "▶")

# -----------------------------
# Main Window
# -----------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.timeline = None
        self.GUI = None
        self.setWindowTitle("Diplotocus GUI")

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Vertical)
        layout.setContentsMargins(0, 0, 0, 0)

        self.base_path = '/Users/titanbin/Desktop/Python/Diplotocus/Unnamed/Unnamed_{}.png'
        self.preview = PreviewWidget(self.base_path,self)
        self.preview.setMinimumHeight(200)
        self.preview.setMaximumHeight(800)
        splitter.addWidget(self.preview)

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0,0,0,0)
        controls_layout.setSpacing(0)

        self.play_controls = PlayControls(self)
        controls_layout.addWidget(self.play_controls)

        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        self.list_widget = PaletteList()
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setStyleSheet("""
            QListWidget::item {
                height: 30px;
            }
        """)

        self.list_widget.addItem(PaletteListItem("Translate",color='#4A90E2'))
        self.list_widget.addItem(PaletteListItem("Rotate",color='#50E3C2'))
        self.list_widget.addItem(PaletteListItem("Scale",color='#F5A623'))
        self.list_widget.addItem(PaletteListItem("Tween",color='#999999'))
        self.list_widget.addItem(PaletteListItem("Morph",color='#999999'))
        self.list_widget.setDragEnabled(True)
        self.list_widget.setFixedWidth(120)
        bottom_layout.addWidget(self.list_widget)

        self.timeline = TimelineView()
        self.timeline.window = self
        self.timeline.setMouseTracking(True)
        self.timeline.resize_handle.setAcceptHoverEvents(True)
        bottom_layout.addWidget(self.timeline)

        self.timeline.time_pin.handle.signals.handleMoved.connect(self.preview.on_pin_moved)
        #self.timeline.time_pin.handle.signals.handleMoved.connect(self.preview.before_image_ready)
        self.preview.worker.imageReady.connect(self.timeline.add_rendered_frame)
        self.timeline.controls = self.play_controls
        self.preview.timeline = self.timeline

        self.play_controls.time_pin = self.timeline.time_pin
        self.play_controls.toStart.connect(self.timeline.on_to_start)
        self.play_controls.toEnd.connect(self.timeline.on_to_end)
        self.play_controls.playPressed.connect(self.timeline.on_play)
        self.play_controls.pausePressed.connect(self.timeline.on_pause)
        self.play_controls.stepForward.connect(self.timeline.on_step_forward)
        self.play_controls.stepBackward.connect(self.timeline.on_step_backward)
        self.play_controls.loop.connect(self.timeline.on_loop)
        self.play_controls.saveVideo.connect(self.timeline.save_video)

        controls_layout.addWidget(bottom_widget)
        splitter.addWidget(controls_widget)

        splitter.setSizes([525, 200])

        layout.addWidget(splitter)
        
        shortcut_P = QShortcut(QKeySequence("P"), self)
        shortcut_Q = QShortcut(QKeySequence("Q"), self)
        shortcut_P.activated.connect(self.on_p_pressed)
        shortcut_Q.activated.connect(self.on_q_pressed)

        self.move_to_screen()

    def move_to_screen(self, screen_index=1):
        screens = QGuiApplication.screens()

        if len(screens) > screen_index:
            geo = screens[screen_index].availableGeometry()
            self.move(geo.left(), geo.top())

        self.show()

    def on_p_pressed(self):
        print('---------------')
        #print('rendering',self.timeline.time_pin.rendering_frames)
        #print('rendered ',self.timeline.rendered_frames)
        #print(self.timeline.time_pin.was_paused_automatically)
        for obj in self.GUI.plot_objects:
                print(obj['object'].anims)
        print(self.GUI.seq.ax.lines)
        print(self.GUI.seq.ax.collections)
        print('---------------')

    def on_q_pressed(self):
        print('---------------')
        self.timeline.derender_frames(0)

    def closeEvent(self, event):
        self.preview.close()
        super().closeEvent(event)

# -----------------------------
# Run
# -----------------------------
class GUI():
    def __init__(self,seq,plot_objects=[]):
        self.app = QApplication()
        self.seq = seq
        self.plot_objects = plot_objects
        self.window = MainWindow()
        self.window.GUI = self
        self.window.resize(1000, 800)
        self.app.setWindowIcon(QIcon("/Users/titanbin/Desktop/Python/Diplotocus/diplotocus/logo.png"))
        #screen_geometry = self.app.primaryScreen().availableGeometry()
        #x = (screen_geometry.width() - self.window.width()) // 2
        #y = (screen_geometry.height() - self.window.height()) // 2
        #self.window.move(x, y)
        self.window.showMaximized()

    def add_plot_objects(self,new_plot_objects):
        if not isinstance(new_plot_objects,list):
            raise TypeError('new_plot_objects must be a list.')
        self.plot_objects += new_plot_objects

    def open(self):
        sys.exit(self.app.exec())

TIMELINE_WIDTH = 1000
MIN_TIMELINE_WIDTH = 100
NUM_ROWS = 4
CLIP_WIDTH = 120
LEFT_MARGIN = 0
EDGE_GRAB = 6
MIN_CLIP_WIDTH = 1
TOP_MARGIN = 20
BOTTOM_MARGIN = 20

#how to use this :
#would load diplotocus.GUI
#push your data to the interface like :
# interface.upload(name='data1',data=np.array(...))
# interface.open()

# eventually, the goal is that you'd also be able to load a sequence that has animations in it and it would populate the timelin    e