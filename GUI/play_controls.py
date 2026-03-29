from PySide6.QtWidgets import QPushButton, QWidget, QHBoxLayout
from PySide6.QtCore import Qt, Signal

class PlayControls(QWidget):
    playPressed = Signal()
    pausePressed = Signal()
    stepForward = Signal()
    stepBackward = Signal()
    toStart = Signal()
    toEnd = Signal()
    loop = Signal()
    saveVideo = Signal()
    clear = Signal(int)
    speed = Signal()
    saveProject = Signal()

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

        self.btn_save_project = QPushButton('↓')
        self.btn_save_project.setToolTip("Save project")
        self.btn_save_project.clicked.connect(self.saveProject.emit)

        self.btn_clear = QPushButton('⊗')
        self.btn_clear.setToolTip("Clear rendered frames")
        self.btn_clear.clicked.connect(lambda: self.clear.emit(0))

        self.btn_speed = QPushButton("x1")
        self.btn_speed.setToolTip("Change speed")
        self.btn_speed.clicked.connect(self.speed.emit)

        size = 36
        for btn in (self.btn_start, self.btn_back, self.btn_play,
                    self.btn_forward, self.btn_end, self.btn_loop,
                    self.btn_save_video, self.btn_save_project, self.btn_clear, self.btn_speed):
            btn.setFixedSize(size, size)
            btn.setFocusPolicy(Qt.NoFocus)

        layout.addStretch(1)

        layout.addWidget(self.btn_clear)

        spacer = QWidget()
        spacer.setFixedWidth(self.btn_back.width() / 3)
        layout.addWidget(spacer)

        layout.addWidget(self.btn_speed)
        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_back)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_forward)
        layout.addWidget(self.btn_end)
        layout.addWidget(self.btn_loop)

        spacer = QWidget()
        spacer.setFixedWidth(self.btn_back.width() / 3)
        layout.addWidget(spacer)

        layout.addWidget(self.btn_save_video)
        layout.addWidget(self.btn_save_project)

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
