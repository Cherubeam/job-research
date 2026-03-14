"""Thread-safe logging handler that captures log messages for the Gradio UI."""

import logging
import threading


class LogCaptureHandler(logging.Handler):
    """Accumulates formatted log messages for display in the UI."""

    def __init__(self, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._messages: list[str] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        with self._lock:
            self._messages.append(msg)

    def get_latest(self) -> str | None:
        with self._lock:
            return self._messages[-1] if self._messages else None

    def get_all(self) -> str:
        with self._lock:
            return "\n".join(self._messages)

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
