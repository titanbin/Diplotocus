import sys
import os
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QRectF
from PySide6.QtGui import QIcon
from diplotocus.GUI.main_window import MainWindow
from diplotocus.GUI.timeline_clip import TimelineClip

class GUI():
    def __init__(self, seq, plot_objects=[]):
        self.app = QApplication()
        self.seq = seq
        self.plot_objects = plot_objects
        self.window = MainWindow(GUI=self)
        self.window.resize(1000, 800)
        full_path = os.path.dirname(os.path.abspath(__file__))
        self.app.setWindowIcon(QIcon(full_path + "/logo.png"))
        self.window.showMaximized()
        self.load_anims()

    def load_anims(self):
        for obj in self.plot_objects:
            for anim in obj['object'].anims:
                name = anim['name'].capitalize()
                for row in range(3):
                    rect = QRectF(
                        anim['delay'], self.window.timeline.row_to_y(row),
                        anim['duration'], self.window.timeline.row_height
                    )
                    if self.window.timeline.check_overlap(None, rect) == False:
                        clip = TimelineClip(self.window.timeline, anim['delay'], row, name, width=anim['duration'], open_settings=False)
                        clip.plot_object = obj
                        clip.setRect(QRectF(clip.rect().left(), clip.rect().top(), anim['duration'], clip.rect().height()))
                        clip.anims = [anim]
                        clip.update_labels()
                        self.window.timeline.scene_obj.addItem(clip)
                        break

    def add_plot_objects(self, new_plot_objects):
        if not isinstance(new_plot_objects, list):
            raise TypeError('new_plot_objects must be a list.')
        self.plot_objects += new_plot_objects

    def open(self):
        sys.exit(self.app.exec())

    def save_project(self):
        dialog = QFileDialog(self.window, "Save file")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)
        if dialog.exec():
            filename = dialog.selectedFiles()[0]
            self.window.GUI.seq.save_project(filename)
