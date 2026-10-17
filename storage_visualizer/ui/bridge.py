from PySide6.QtCore import QObject, Signal


class ResultBridge(QObject):
    """Created on the UI thread; emitting from worker threads queues delivery to it."""

    volume_ready = Signal(object)
