import signal
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
    app.aboutToQuit.connect(refresher.stop)  # before the bridge is torn down
    refresher.start()  # first refresh before show(): window opens at its final size
    window.show()

    # Python can't run its SIGINT handler while app.exec() blocks in C++, so Ctrl+C
    # would only land at the next tick, as a KeyboardInterrupt traceback inside
    # refresh(). SIG_DFL terminates immediately; the graceful quit (aboutToQuit ->
    # Refresher.stop) is closing the window. No wake-up timer: idle CPU stays zero.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    return app.exec()
