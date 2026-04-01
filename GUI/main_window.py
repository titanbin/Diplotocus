import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QHBoxLayout, QListWidget, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QGuiApplication
from .palette import PaletteList, PaletteListItem
from .play_controls import PlayControls
from .preview import PreviewWidget
from .timeline import TimelineView

class MainWindow(QWidget):
    def __init__(self, GUI):
        super().__init__()
        self.timeline = None
        self.GUI = GUI
        self.setWindowTitle("Diplotocus GUI")

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Vertical)
        layout.setContentsMargins(0, 0, 0, 0)

        full_path = os.path.dirname(os.path.abspath(__file__))
        self.base_path = GUI.seq.full_path + '/Unnamed/Unnamed_{}.png'
        self.preview = PreviewWidget(self.base_path, self)
        parent_dir = os.path.dirname(full_path)
        self.preview.load_image(parent_dir + '/logo_bg.png')
        self.preview.setMinimumHeight(200)
        self.preview.setMaximumHeight(800)
        splitter.addWidget(self.preview)

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)

        self.play_controls = PlayControls(self)
        controls_layout.addWidget(self.play_controls)

        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_widget.setMinimumHeight(215)

        self.list_widget = PaletteList()
        self.list_widget.setSpacing(1.5)
        
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setStyleSheet("""
            QListWidget::item {
                height: 32px;
            }
        """)

        self.list_widget.addItem(PaletteListItem("Translate", color='#4A90E2'))
        self.list_widget.addItem(PaletteListItem("Rotate", color='#D81159'))
        self.list_widget.addItem(PaletteListItem("Scale", color='#F5A623'))
        self.list_widget.addItem(PaletteListItem("Tween", color='#1CC4B6'))
        self.list_widget.addItem(PaletteListItem("Morph", color='#A14DA0'))
        self.list_widget.addItem(PaletteListItem("Draw", color="#44913F"))
        self.list_widget.setDragEnabled(True)
        self.list_widget.setFixedWidth(80)

        bottom_layout.addWidget(self.list_widget)
        bottom_layout.setSpacing(0)

        timeline_margin = QWidget()
        
        timeline_margin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        timeline_margin.setStyleSheet("background: #171717;")
        bottom_layout.addWidget(timeline_margin)

        self.timeline = TimelineView()
        self.timeline.window = self
        self.timeline.setMouseTracking(True)
        self.timeline.resize_handle.setAcceptHoverEvents(True)
        bottom_layout.addWidget(self.timeline)

        self.timeline.time_pin.handle.signals.handleMoved.connect(self.preview.on_pin_moved)
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
        self.play_controls.clear.connect(self.timeline.derender_frames)
        self.play_controls.speed.connect(self.timeline.change_speed)
        self.play_controls.saveProject.connect(self.GUI.save_project)

        controls_layout.addWidget(bottom_widget)
        splitter.addWidget(controls_widget)

        splitter.setSizes([510, 215])

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
