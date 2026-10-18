import sys

import psutil
from PySide6.QtWidgets import QApplication

from storage_visualizer.core.enumerator import enumerate_mounts
from storage_visualizer.core.usage import UsageProbe
from storage_visualizer.ui.bridge import ResultBridge
from storage_visualizer.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("storage-visualizer")
    app.setDesktopFileName("storage-visualizer")

    mounts = enumerate_mounts(psutil.disk_partitions(all=True))

    window = MainWindow(mounts)
    bridge = ResultBridge()  # keep referenced until app.exec() returns
    bridge.volume_ready.connect(window.update_volume)

    window.show()
    UsageProbe().probe_all(mounts, bridge.volume_ready.emit)

    return app.exec()
