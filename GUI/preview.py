import queue
from PySide6.QtWidgets import QWidget, QLabel, QSizePolicy
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QTimer
from PySide6.QtGui import QPixmap

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
        self.worker = PreviewWorker(base_path, self.window_widget)
        self.worker.moveToThread(self.thread)

        self.worker.renderImage.connect(self.render_frame)
        self.worker.imageReady.connect(self.on_image_ready)
        self.worker.beforeImageReady.connect(self.before_image_ready)

        self.thread.start()

    def render_frame(self, frame):
        self.window_widget.GUI.seq.clean_all()
        objs = [el['object'] for el in self.window_widget.GUI.plot_objects]
        self.window_widget.GUI.seq.plot(objs, x=frame)

    def on_pin_moved(self, _=None):
        frame = int(self.timeline.time_pin.frame_x)
        if frame not in self.timeline.rendered_frames:
            self.worker.enqueue(frame)
        else:
            path = self.base_path.format(frame)
            self.on_image_ready(path, frame)

    def before_image_ready(self, state, frame):
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
