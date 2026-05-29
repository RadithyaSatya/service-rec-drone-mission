from __future__ import annotations

import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import Settings
from app.streaming.pipeline import StreamingController
from app.utils.logger import get_logger

LOGGER = get_logger(__name__)


PLAYER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UAV HLS Player</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #09111a;
      --panel: #101b28;
      --text: #e7f0f7;
      --muted: #8ea3b7;
      --accent: #4dd0a8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "SF Mono", Menlo, Consolas, monospace;
      background: radial-gradient(circle at top, #17324a 0%, var(--bg) 55%);
      color: var(--text);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }
    .shell {
      width: min(960px, 100%);
      background: rgba(16, 27, 40, 0.94);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.35);
    }
    .bar {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .status {
      color: var(--accent);
      font-size: 13px;
    }
    .url {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
      text-align: right;
    }
    video {
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #000;
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="bar">
      <div class="status" id="status">connecting</div>
      <div class="url" id="url"></div>
    </div>
    <video id="video" controls autoplay muted playsinline></video>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <script>
    const video = document.getElementById("video");
    const statusEl = document.getElementById("status");
    const urlEl = document.getElementById("url");
    let hls;

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function attachNative(playlistUrl) {
      video.src = playlistUrl;
      video.addEventListener("loadedmetadata", () => {
        video.play().catch(() => {});
        setStatus("playing");
      }, { once: true });
    }

    function attachHls(playlistUrl) {
      hls = new Hls({
        lowLatencyMode: true,
        liveSyncDurationCount: 2,
        maxLiveSyncPlaybackRate: 1.2,
        backBufferLength: 10,
      });
      hls.loadSource(playlistUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {});
        setStatus("playing");
      });
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          setStatus(`reconnecting: ${data.type}`);
          hls.destroy();
          setTimeout(connect, 1500);
        }
      });
    }

    async function connect() {
      setStatus("connecting");
      const info = await fetch("/stream-info").then((response) => response.json());
      const playlistUrl = info.hls_url;
      urlEl.textContent = playlistUrl;
      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        attachNative(playlistUrl);
        return;
      }
      if (window.Hls && Hls.isSupported()) {
        attachHls(playlistUrl);
        return;
      }
      setStatus("hls unsupported");
    }

    connect();
  </script>
</body>
</html>
"""


def create_app(settings: Settings, controller: StreamingController) -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Path(settings.hls_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.records_dir).mkdir(parents=True, exist_ok=True)

    app.mount("/hls", StaticFiles(directory=settings.hls_dir), name="hls")
    app.mount("/records", StaticFiles(directory=settings.records_dir), name="records")

    @app.get("/health")
    def health() -> JSONResponse:
        playlist = controller.hls_path()
        return JSONResponse(
            {
                "status": "ok",
                "runtime_state": controller.current_state().value,
                "hls_url": controller.hls_url(),
                "playlist_exists": playlist.exists(),
                "playlist_size": playlist.stat().st_size if playlist.exists() else 0,
            }
        )

    @app.get("/stream-info")
    def stream_info() -> JSONResponse:
        return JSONResponse(
            {
                "drone_id": controller.drone_id,
                "hls_url": controller.hls_url(),
                "player_url": settings.player_url,
            }
        )

    @app.get("/player")
    def player() -> HTMLResponse:
        return HTMLResponse(PLAYER_HTML)

    return app


class LocalHttpServer:
    def __init__(self, settings: Settings, controller: StreamingController) -> None:
        self._settings = settings
        self._controller = controller
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        app = create_app(self._settings, self._controller)
        config = uvicorn.Config(
            app,
            host=self._settings.server_host,
            port=self._settings.server_port,
            log_level=self._settings.log_level.lower(),
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="fastapi-server", daemon=True)
        self._thread.start()
        LOGGER.info(
            "http server started",
            extra={"context": {"host": self._settings.server_host, "port": self._settings.server_port}},
        )

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
