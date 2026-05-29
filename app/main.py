from __future__ import annotations

import signal
import threading
import time

from app.config.settings import load_settings
from app.http_server import LocalHttpServer
from app.streaming.pipeline import StreamingController
from app.utils.logger import configure_logging, get_logger
from app.websocket.client import TelemetryWebSocketClient

LOGGER = get_logger(__name__)


def main() -> int:
    settings = load_settings()
    configure_logging(settings.log_level, settings.app_log_path)

    controller = StreamingController(settings)
    http_server = LocalHttpServer(settings, controller)
    ws_client = TelemetryWebSocketClient(settings, controller)
    stop_event = threading.Event()

    def _handle_signal(signum, frame) -> None:
        del frame
        LOGGER.info("shutdown signal received", extra={"context": {"signum": signum}})
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    controller.start()
    http_server.start()
    ws_client.start()

    try:
        while not stop_event.is_set():
            controller.tick()
            time.sleep(1)
    finally:
        ws_client.stop()
        http_server.stop()
        controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
