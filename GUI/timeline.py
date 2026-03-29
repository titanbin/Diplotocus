from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QFileDialog
)
from PySide6.QtCore import Qt, QRectF, QEvent
from PySide6.QtGui import QPen, QBrush, QColor
from .constants import TOP_MARGIN, BOTTOM_MARGIN, NUM_ROWS, CLIP_WIDTH, LEFT_MARGIN, MIN_TIMELINE_WIDTH, TIMELINE_WIDTH
from .timeline_controls import TimePin, TimelineResizeHandle
from .timeline_clip import TimelineClip

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
        from PySide6.QtCore import QTimer
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(1000 // (30 * 3))
        self.play_timer.timeout.connect(self.advance_frame)

        self.rendered_frames = []
        self.rendered_rects = []

        self.background_rect = self.scene_obj.addRect(
            self.scene_obj.sceneRect(),
            pen=QPen(Qt.NoPen)
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
                        for anim in item.anims:
                            item.plot_object['object'].anims.remove(anim)
                    self.scene_obj.removeItem(item)
                    del item
            event.accept()
            self.compute_rightmost_clip()

            self.derender_frames(x_min)

            self.render_current_frame(x_min, x_max)
            return

        super().keyPressEvent(event)

    def render_current_frame(self, xmin=-1, xmax=None):
        if xmax is None:
            xmax = self.timeline_width + 2
        current_frame = self.time_pin.frame_x
        if xmin <= current_frame <= xmax:
            if current_frame in self.rendered_frames:
                self.rendered_frames.remove(current_frame)
            self.window.preview.on_pin_moved()

    def add_rendered_frame(self, _, frame):
        if frame not in self.rendered_frames:
            self.rendered_frames.append(frame)

            rect_exists = any(rect.rect().x() == frame for rect in self.rendered_rects)
            if not rect_exists:
                self.rendered_rects.append(self.scene_obj.addRect(
                    frame, 0, 1, TOP_MARGIN,
                    pen=QPen(Qt.NoPen),
                    brush=QBrush(QColor("#0EA35B"))
                ))

    def derender_frames(self, frame):
        new_rendered_frames = []
        new_rendered_rects = []
        for rendered_frame, rendered_rect in zip(self.rendered_frames, self.rendered_rects):
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
        self.scene_obj.setSceneRect(0, 0, width + 50, self.timeline_height + self.top_margin)
        self.background_rect.setRect(self.scene_obj.sceneRect())
        self.update_resize_handle()
        self.draw_row_lines()

        for item in self.scene_obj.items():
            if isinstance(item, TimelineClip):
                row = self.y_to_row(item.pos().y())
                item.setRect(0, 0, item.rect().width(), self.row_height)
                item.setPos(item.pos().x(), self.row_to_y(row))
        self.time_pin.timeline_width = width

    def resizeEvent(self, event):
        self.timeline_height = self.get_timeline_height()
        self.resize_handle.setRect(
            self.resize_handle.rect().x(),
            (self.timeline_height + self.top_margin - self.resize_handle.height) / 2,
            self.resize_handle.rect().width(),
            self.resize_handle.height
        )

        self.row_height = min(self.timeline_height / self.num_rows, 80)
        self.scene_obj.setSceneRect(0, 0, self.timeline_width, self.timeline_height + self.top_margin)
        self.background_rect.setRect(self.scene_obj.sceneRect())
        self.draw_row_lines()

        self.time_pin.timeline_height = self.timeline_height
        self.time_pin.setLine(0, 0, 0, self.timeline_height)

        for item in self.scene_obj.items():
            if isinstance(item, TimelineClip):
                row = self.y_to_row(item.pos().y())
                item.setRect(0, 0, item.rect().width(), self.row_height)
                item.setPos(item.pos().x(), self.row_to_y(row))
        super().resizeEvent(event)

    def compute_rightmost_clip(self):
        self.rightmost_clip = 0
        for clip in self.scene_obj.items():
            if isinstance(clip, TimelineClip):
                if clip.pos().x() + clip.rect().width() > self.rightmost_clip:
                    self.rightmost_clip = clip.pos().x() + clip.rect().width()

    def draw_row_lines(self):
        if len(self.row_lines) == 0:
            self.create_row_lines()
        else:
            for i, rect in enumerate(self.row_lines):
                y1 = self.top_margin + i * self.row_height
                y2 = self.top_margin + (i + 1) * self.row_height
                rect.setPos(rect.x(), y1)
                rect.setRect(0, 0, self.timeline_width, y2 - y1)

    def create_row_lines(self):
        for i in range(self.num_rows):
            y1 = self.top_margin + i * self.row_height
            y2 = self.top_margin + (i + 1) * self.row_height
            rect = self.scene_obj.addRect(
                0, y1, self.timeline_width, y2,
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
                    self.window.GUI.seq.x = int(self.timeline_width + 1)
                    dialog = QFileDialog(self, "Save file")
                    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
                    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)
                    if dialog.exec():
                        filename = dialog.selectedFiles()[0]
                        if filename.split('.')[-1] in ['mp4', 'mov']:
                            self.window.GUI.seq.save_video(path=filename, clean=False)
                        else:
                            self.window.GUI.seq.save_video(clean=False)

    def on_loop(self):
        self.loop = not self.loop

    def row_to_y(self, row):
        return self.top_margin + row * self.row_height

    def y_to_row(self, y):
        return int(round((y - self.top_margin) / self.row_height))

    def change_speed(self):
        speed = self.window.play_controls.btn_speed.text()[1:]
        speeds = ['0.1', '0.5', '1']
        new_speed = speeds[(speeds.index(speed) + 1) % len(speeds)]
        self.window.play_controls.btn_speed.setText('x{}'.format(new_speed))
        self.play_timer.setInterval(1000 / float(new_speed) // (30 * 3))

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
        self.time_pin.set_frame(self.time_pin.frame_x + 1)
        if self.time_pin.is_playing:
            self.time_pin.is_playing = False
            self.play_timer.stop()
            self.controls.set_playing(False)

    def on_step_backward(self):
        self.window.play_controls.btn_save_video.setChecked(False)
        self.time_pin.was_paused_automatically = False
        self.time_pin.set_frame(self.time_pin.frame_x - 1)
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
        else:
            self.on_pause()

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
        x = max(LEFT_MARGIN, min(scene_pos.x() - CLIP_WIDTH / 2, self.timeline_width))
        clip_name = event.mimeData().text()

        clip = TimelineClip(self, x, row, clip_name)
        rect = QRectF(
            x, self.row_to_y(row),
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
                    item.pos().x(), item.pos().y() + 1,
                    item.rect().width(), item.rect().height() - 2
                )
                if test_rect.intersects(other_rect):
                    return True
        return False
