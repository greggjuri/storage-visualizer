import sys

from PySide6.QtWidgets import QApplication

from storage_visualizer.ui.bridge import ResultBridge
from storage_visualizer.ui.main_window import MainWindow
from storage_visualizer.ui.refresher import Refresher


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("storage-visualizer")
    app.setDesktopFileName("storage-visualizer")

    window = MainWindow()
    bridge = ResultBridge()
    bridge.volume_ready.connect(window.update_volume)
    refresher = Refresher(window, bridge)  # keep referenced until app.exec() returns
    refresher.start()  # first refresh before show(): window opens at its final size
    window.show()

    return app.exec()
