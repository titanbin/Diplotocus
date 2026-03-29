import sys
import ast
from PySide6.QtWidgets import (
    QGraphicsTextItem, QGraphicsRectItem, QDialog, QVBoxLayout, QPushButton,
    QLineEdit, QFormLayout, QComboBox, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QBrush, QPen, QPixmap, QFontMetrics, QFont, QPainter, QPainterPath
)
from .constants import CLIP_WIDTH, EDGE_GRAB, MIN_CLIP_WIDTH, LEFT_MARGIN, NUM_ROWS, TOP_MARGIN
import diplotocus.easings as easings


class ElidedGraphicsTextItem(QGraphicsTextItem):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.parent = parent
        self.full_text = text
        self.max_width = 0

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
        self.setTextWidth(-1)


class TimelineClip(QGraphicsRectItem):
    def __init__(self, timeline, x, row, name, width=None, open_settings=True):
        if width == None:
            width = CLIP_WIDTH
        self.timeline = timeline
        self.plot_object = None
        super().__init__(0, 0, width, self.timeline.row_height)
        self.just_spawned = True

        self.base_color = '#999999'
        for i in range(self.timeline.window.list_widget.count()):
            item = self.timeline.window.list_widget.item(i)
            if item.text() == name:
                color = item.background().color().name()
                break

        self.base_color = color
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
        self.anims = []

        self.type_label = ElidedGraphicsTextItem(name, self)
        self.type_label.setDefaultTextColor(Qt.white)
        self.type_label.setPos(5, 5)
        self.type_label.setTextWidth(width - 10)
        self.type_label.setFlag(QGraphicsTextItem.ItemIsSelectable, False)
        self.type_label.setFlag(QGraphicsTextItem.ItemIsFocusable, False)
        font = self.type_label.font()
        font.setBold(True)
        font.setPointSize(13)
        self.type_label.setFont(font)

        self.obj_label = ElidedGraphicsTextItem('', self)
        self.obj_label.setDefaultTextColor(Qt.white)
        self.obj_label.setPos(5, 20)
        self.obj_label.setTextWidth(width - 10)
        self.obj_label.setFlag(QGraphicsTextItem.ItemIsSelectable, False)
        self.obj_label.setFlag(QGraphicsTextItem.ItemIsFocusable, False)

        self.update_labels()

        self._remove_when_added = False

        self.setPos(x, self.timeline.row_to_y(row))

        self.timeline.derender_frames(x)
        self.timeline.render_current_frame(x, x + width)
        if self.timeline.timeline_width < x + width:
            self.timeline.set_timeline_width(x + width)

        if x + width > self.timeline.rightmost_clip:
            self.timeline.rightmost_clip = x + width

        self.background_pixmap = QPixmap('diplotocus/src/btn/btn_bg_{}.png'.format(name))

        if open_settings:
            self.open_settings()

    def update_labels(self):
        self.type_label.set_text(self.name)
        if self.plot_object is None:
            text = ''
        else:
            text = self.plot_object['name']
        self.obj_label.set_text(text)

    def add_plot_object(self, name, x, duration=None):
        if duration is None:
            duration = self.rect().width() + 1
        if self.plot_object is None:
            return
        obj = self.plot_object['object']
        len_before = len(obj.anims)
        if name == "Translate":
            obj.translate((0, 0), (1, 1), duration=duration, delay=x)
        elif name == "Rotate":
            obj.rotate(0, 360, duration=duration, delay=x)
        elif name == "Scale":
            obj.scale((1, 1), (2, 2), duration=duration, delay=x)
        elif name == "Morph":
            new_x = self.plot_object['new_x']
            new_y = self.plot_object['new_y']
            obj.morph(new_x=new_x, new_y=new_y, duration=duration, delay=x)
        elif name == 'Tween':
            obj.tweens(properties=[], starts=[], ends=[], duration=duration, delay=x)
        elif name == 'Draw':
            obj.draw(duration=duration, delay=x)
        self.anims = obj.anims[len_before:]

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
                    if self.validate_resize(self.pos().x() + delta, new_width):
                        self.setRect(delta, 0, new_width, self.timeline.row_height)

            elif self.resize_right:
                new_width = self.orig_rect.width() + delta
                if new_width >= MIN_CLIP_WIDTH:
                    if self.validate_resize(self.pos().x(), new_width):
                        self.setRect(0, 0, new_width, self.timeline.row_height)

            if self.plot_object is not None:
                for anim in self.anims:
                    anim_i = self.plot_object['object'].anims.index(anim)
                    self.plot_object['object'].anims[anim_i]['duration'] = new_width + 1
            self.timeline.derender_frames(self.pos().x())

            self.type_label.set_max_width()
            self.type_label.setPos(self.rect().x() + 5, self.type_label.pos().y())
            self.obj_label.set_max_width()
            self.obj_label.setPos(self.rect().x() + 5, self.obj_label.pos().y())
        else:
            super().mouseMoveEvent(event)

    def hoverMoveEvent(self, event):
        x = event.pos().x()
        if x < EDGE_GRAB or x > self.rect().width() - EDGE_GRAB:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtWidgets import QGraphicsItem

        if change == QGraphicsItem.ItemSceneHasChanged:
            if self._remove_when_added and self.scene() is not None:
                self.scene().removeItem(self)
                self._remove_when_added = False
        if change == QGraphicsRectItem.ItemPositionChange:
            if self.just_spawned:
                self.just_spawned = False
                return super().itemChange(change, value)
            new_pos = value

            x = max(
                LEFT_MARGIN,
                min(new_pos.x(), self.timeline.timeline_width - self.rect().width())
            )

            row = max(0, min(NUM_ROWS - 1, self.timeline.y_to_row(new_pos.y())))
            y = self.timeline.row_to_y(row)

            proposed_pos = QPointF(x, y)

            test_rect = QRectF(
                x, y,
                self.rect().width(), self.rect().height()
            )
            if self.timeline.check_overlap(self, test_rect):
                return self.pos()

            if self.plot_object is not None:
                for anim in self.anims:
                    anim_i = self.plot_object['object'].anims.index(anim)
                    self.plot_object['object'].anims[anim_i]['delay'] = proposed_pos.x()
            frames_to_derender = min(self.pos().x(), proposed_pos.x())
            self.timeline.derender_frames(frames_to_derender)
            return proposed_pos

        return super().itemChange(change, value)

    def paint(self, painter, option, widget):
        color = QColor(self.base_color)
        if self.isSelected():
            color = color.darker(150)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        radius = 5
        painter.drawRoundedRect(self.rect(), radius, radius)
        new_width = self.rect().width()
        new_height = min(self.rect().height(), self.background_pixmap.rect().height())
        cropped_pixmap = self.background_pixmap.copy(
            0,
            (self.background_pixmap.rect().height() - new_height) / 2,
            new_width,
            new_height + 4
        )
        mask = QPixmap(new_width, new_height + 1)
        mask.fill(Qt.transparent)
        mask_painter = QPainter(mask)
        path = QPainterPath()
        path.addRoundedRect(0, 0, new_width, new_height + 1, radius, radius)
        mask_painter.setClipPath(path)
        mask_painter.drawPixmap(0, 0, cropped_pixmap)
        mask_painter.end()

        painter.drawPixmap(self.rect().topLeft(), mask)

        border_color = color.darker(230)
        pen = QPen(border_color)
        painter.setBrush(Qt.NoBrush)
        width = 2
        pen.setWidth(width)
        painter.setPen(pen)

        rect = self.rect()

        path = QPainterPath()
        path.moveTo(
            rect.left() + (1 - 0.707) * radius,
            rect.bottom() - radius - width / 2 + 0.707 * radius
        )
        path.arcTo(
            rect.left(), rect.bottom() - 2 * radius - width / 2,
            2 * radius, 2 * radius,
            180 + 45, 45
        )
        path.lineTo(rect.right() - radius, rect.bottom() - width / 2)
        path.arcTo(
            rect.right() - 2 * radius - width / 2 + 3, rect.bottom() - 2 * radius - width / 2 + 2,
            2 * radius - 3, 2 * radius - 2,
            270, 90
        )
        path.lineTo(rect.right() - width / 2, rect.top() + radius)
        path.arcTo(
            rect.right() - 2 * radius - width / 2, rect.top(),
            2 * radius, 2 * radius,
            0, 45
        )
        painter.drawPath(path)

        border_color = color.lighter(100)
        pen = QPen(border_color)
        painter.setBrush(Qt.NoBrush)
        width = 2
        pen.setWidth(width)
        painter.setPen(pen)

        rect = self.rect()

        path = QPainterPath()
        path.moveTo(
            rect.left() + (1 - 0.707) * radius,
            rect.bottom() - radius - width / 2 + 0.707 * radius
        )
        path.arcTo(
            rect.left(), rect.bottom() - 2 * radius - width / 2,
            2 * radius, 2 * radius,
            180 + 45, -45
        )
        path.lineTo(rect.left(), rect.top() + radius)
        path.arcTo(
            rect.left(), rect.top() + width / 2,
            2 * radius, 2 * radius,
            180, -90
        )
        path.lineTo(rect.right() - radius, rect.top() + width / 2)
        path.arcTo(
            rect.right() - 2 * radius - width / 2, rect.top() + width / 2,
            2 * radius, 2 * radius,
            90, -45
        )
        painter.drawPath(path)

    def mouseReleaseEvent(self, event):
        self.resize_left = False
        self.resize_right = False
        self.setCursor(Qt.OpenHandCursor)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
        if self.rect().x() != 0:
            self.setPos(self.pos().x() + self.rect().x(), self.pos().y())
            self.setRect(0, 0, self.rect().width(), self.rect().height())
            self.type_label.setPos(self.rect().x() + 5, self.type_label.pos().y())
            self.obj_label.setPos(self.rect().x() + 5, self.obj_label.pos().y())

        self.timeline.render_current_frame(self.pos().x(), self.pos().x() + self.rect().width())
        self.timeline.compute_rightmost_clip()
        super().mouseReleaseEvent(event)

    def validate_resize(self, new_x, new_width):
        from PySide6.QtCore import QRectF
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
        self.properties = None

        self.make_layout(self.clip.name)

        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        self.main_layout.addWidget(btn)

        self.rejected.connect(self.on_dialog_closed)

    def on_dialog_closed(self):
        if self.clip.plot_object is not None:
            for anim in self.clip.anims:
                self.clip.plot_object['object'].anims.remove(anim)
        self.clip._remove_when_added = True

    def accept(self):
        to_derender = False

        obj_i = self.plot_object.currentData()
        if obj_i == 0:
            new_plot_object = None
        else:
            new_plot_object = self.clip.timeline.window.GUI.plot_objects[obj_i - 1]

        if new_plot_object != self.clip.plot_object:
            self.clip.timeline.derender_frames(0)
            was_none = self.clip.plot_object is None
            if not was_none:
                for anim in self.clip.anims:
                    self.clip.plot_object['object'].anims.remove(anim)
                self.clip.anims = []

            self.clip.plot_object = new_plot_object

            if was_none:
                self.clip.add_plot_object(self.clip.name, self.clip.pos().x(), self.clip.rect().width())
            elif self.clip.plot_object is not None:
                self.clip.plot_object['object'].anims += self.clip.anims

        new_easing = getattr(easings, self.easing.currentText())()
        new_name = new_easing.__class__.__name__
        if len(self.clip.anims) > 0:
            old_name = self.clip.anims[0]['easing'].__class__.__name__
            if new_name != old_name:
                for anim in self.clip.anims:
                    anim['easing'] = new_easing
                to_derender = True

        if self.clip.plot_object is not None:
            if self.clip.name == 'Translate':
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anims[0])
                prop = self.clip.plot_object['object'].anims[anim_i]

                start_x, start_y, end_x, end_y = self.sanitize_input(
                    [self.start_x, self.start_y, self.end_x, self.end_y],
                    lambda x: float(x),
                    [0, 0, 1, 1]
                )

                if prop['start'][0] != start_x or prop['start'][1] != start_y:
                    to_derender = True
                    prop['start'] = (start_x, start_y)
                if prop['end'][0] != end_x or prop['end'][1] != end_y:
                    to_derender = True
                    prop['end'] = (end_x, end_y)
            elif self.clip.name == 'Rotate':
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anims[0])
                prop = self.clip.plot_object['object'].anims[anim_i]

                start, end = self.sanitize_input(
                    [self.start_x, self.end_x],
                    lambda x: float(x),
                    [0, 360]
                )

                if prop['start'] != start:
                    to_derender = True
                    prop['start'] = start
                if prop['end'] != end:
                    to_derender = True
                    prop['end'] = end
            elif self.clip.name == 'Scale':
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anims[0])
                prop = self.clip.plot_object['object'].anims[anim_i]

                start_x, start_y, end_x, end_y = self.sanitize_input(
                    [self.start_x, self.start_y, self.end_x, self.end_y],
                    lambda x: float(x),
                    [1, 1, 2, 2]
                )

                if prop['start'][0] != start_x or prop['start'][1] != start_y:
                    to_derender = True
                    prop['start'] = (start_x, start_y)
                if prop['end'][0] != end_x or prop['end'][1] != end_y:
                    to_derender = True
                    prop['end'] = (end_x, end_y)
            elif self.clip.name == 'Tween':
                to_derender = True
                properties = ast.literal_eval(self.properties.text())
                starts = ast.literal_eval(self.start_x.text())
                ends = ast.literal_eval(self.end_x.text())
                properties = self.clip.plot_object['object'].get_main_alias(properties)
                properties, starts, ends = self.clip.plot_object['object'].sanitize_colors(properties, starts, ends)
                for i, anim in enumerate(self.clip.anims):
                    anim_i = self.clip.plot_object['object'].anims.index(anim)
                    prop = self.clip.plot_object['object'].anims[anim_i]

                    property = properties[i]
                    start = starts[i]
                    end = ends[i]

                    prop['property'] = property
                    prop['start'] = start
                    prop['end'] = end
                if len(properties) > len(self.clip.anims):
                    for property, start, end in zip(properties[len(self.clip.anims):], starts[len(self.clip.anims):], ends[len(self.clip.anims):]):
                        new_anim = {
                            'name': 'tween',
                            'duration': self.clip.rect().width() + 1,
                            'delay': self.clip.pos().x(),
                            'easing': new_easing,
                            'property': property,
                            'start': start,
                            'end': end,
                            'persistent': self.persistent.isChecked()
                        }
                        len_before = len(self.clip.plot_object['object'].anims)
                        self.clip.plot_object['object'].anims.append(new_anim)
                        self.clip.anims += self.clip.plot_object['object'].anims[len_before:]

        if self.clip.plot_object is not None:
            for i, anim in enumerate(self.clip.anims):
                anim_i = self.clip.plot_object['object'].anims.index(anim)
                prop = self.clip.plot_object['object'].anims[anim_i]
                was_persistent = prop['persistent']
                if was_persistent != self.persistent.isChecked():
                    to_derender = True
                    prop['persistent'] = self.persistent.isChecked()

        self.clip.update_labels()

        if to_derender:
            self.clip.timeline.derender_frames(self.clip.pos().x())
        self.clip.timeline.window.preview.on_pin_moved()
        super().accept()

    def sanitize_input(self, inputs, func, defaults):
        sanitized_inputs = []
        for input, default in zip(inputs, defaults):
            try:
                sanitized_inputs.append(func(input.text()))
            except:
                sanitized_inputs.append(default)
        return sanitized_inputs

    def make_layout(self, type):
        self.setWindowTitle(type + " Settings")

        form = QFormLayout()

        if type == 'Translate':
            if self.clip.plot_object is not None:
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anims[0])
                prop = self.clip.plot_object['object'].anims[anim_i]
                start_x = prop['start'][0]
                start_y = prop['start'][1]
                end_x = prop['end'][0]
                end_y = prop['end'][1]
            else:
                start_x, start_y, end_x, end_y = 0, 0, 1, 1
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
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anims[0])
                prop = self.clip.plot_object['object'].anims[anim_i]
                start = prop['start']
                end = prop['end']
            else:
                start, end = 0, 360

            self.start_x = QLineEdit()
            self.start_x.setText(str(start))
            form.addRow("Start angle (°)", self.start_x)
            self.end_x = QLineEdit()
            self.end_x.setText(str(end))
            form.addRow("End angle (°)", self.end_x)
        elif type == 'Scale':
            if self.clip.plot_object is not None:
                anim_i = self.clip.plot_object['object'].anims.index(self.clip.anims[0])
                prop = self.clip.plot_object['object'].anims[anim_i]
                start_x = prop['start'][0]
                start_y = prop['start'][1]
                end_x = prop['end'][0]
                end_y = prop['end'][1]
            else:
                start_x, start_y, end_x, end_y = 1, 1, 2, 2
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
        elif type == 'Tween':
            properties = []
            starts = []
            ends = []
            if self.clip.plot_object is not None:
                for anim in self.clip.anims:
                    anim_i = self.clip.plot_object['object'].anims.index(anim)
                    prop = self.clip.plot_object['object'].anims[anim_i]
                    properties.append(prop['property'])
                    starts.append(prop['start'])
                    ends.append(prop['end'])

            self.properties = QLineEdit()
            self.properties.setText(str(properties))
            form.addRow("Property names", self.properties)
            self.start_x = QLineEdit()
            self.start_x.setText(str(starts))
            form.addRow("Start values", self.start_x)
            self.end_x = QLineEdit()
            self.end_x.setText(str(ends))
            form.addRow("End values", self.end_x)
        elif type == 'Draw':
            pass

        self.easing = QComboBox()
        self.easing.addItems(easings.available_easings)

        easing = None
        if len(self.clip.anims) > 0:
            easing = self.clip.anims[0]['easing']
        if easing is None:
            easing = 'easeLinear'
        else:
            easing = easing.__class__.__name__
        index = self.easing.findText(easing)
        if index >= 0:
            self.easing.setCurrentIndex(index)

        form.addRow('Easing', self.easing)

        self.plot_object = QComboBox()
        self.plot_object.addItem('None', 0)
        for i, obj in enumerate(self.clip.timeline.window.GUI.plot_objects):
            if type != 'Morph' or ('new_x' in obj and 'new_y' in obj):
                self.plot_object.addItem(obj['name'], i + 1)
        if self.clip.plot_object is not None:
            index = self.plot_object.findText(self.clip.plot_object['name'])
        else:
            index = 0

        if index >= 0:
            self.plot_object.setCurrentIndex(index)

        form.addRow('Object', self.plot_object)

        self.persistent = QCheckBox()

        if self.clip.plot_object is not None:
            anim_i = self.clip.plot_object['object'].anims.index(self.clip.anims[0])
            prop = self.clip.plot_object['object'].anims[anim_i]
            self.persistent.setChecked(prop['persistent'])
        else:
            self.persistent.setChecked(True)

        form.addRow('Persistent', self.persistent)

        self.main_layout.addLayout(form)
