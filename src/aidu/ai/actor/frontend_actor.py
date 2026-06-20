from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class UserInput(BaseModel):
    role: str
    content: str


# ------------------------------------------------------------------
# Frontend Actor
# ------------------------------------------------------------------

class FrontendActor:
    def __init__(
        self,
        name: str,
        director_url: str,
        description: str = "",
    ):
        """
        FrontendActor serves the web frontend and accepts
        browser requests for future processing.

        Browser
            ↓
        FrontendActor
        """

        self.name = name
        self.description = description
        self.director_url = director_url.rstrip("/")
        self.turns: list[dict[str, str]] = []
        self.subscribers: set[queue.Queue[dict[str, str]]] = set()

        self.web_dir = (
            Path(__file__).parent
            / "demo"
        )

        # check if the web_dir exists
        if not self.web_dir.exists():
            raise FileNotFoundError(f"Web directory '{self.web_dir}' does not exist. Please ensure the frontend assets are built and available.")

        self.app = FastAPI(
            title=name,
            description=description,
        )
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._register_routes()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def _publish_turn(self, turn: dict[str, str]):
        self.turns.append(turn)
        for subscriber in list(self.subscribers):
            try:
                subscriber.put_nowait(turn)
            except queue.Full:
                self.subscribers.discard(subscriber)

    def _register_routes(self):

        # --------------------------------------------------
        # Static frontend
        # --------------------------------------------------

        if (self.web_dir / "assets").exists():
            self.app.mount(
                "/assets",
                StaticFiles(
                    directory=self.web_dir / "assets"
                ),
                name="assets",
            )

        @self.app.get("/")
        def index():
            return FileResponse(
                self.web_dir / "index.html",
                headers={"Cache-Control": "no-store"},
            )

        @self.app.get("/app.js")
        def app_js():
            return FileResponse(
                self.web_dir / "app.js",
                media_type="application/javascript",
                headers={"Cache-Control": "no-store"},
            )

        # --------------------------------------------------
        # Health
        # --------------------------------------------------

        @self.app.get("/health")
        def health():
            return {
                "name": self.name,
                "status": "running",
            }

        @self.app.get("/info")
        def info():
            return {
                "name": self.name,
                "description": self.description,
                "director": self.director_url,
                "forwarding": "not implemented",
            }

        # --------------------------------------------------
        # Browser sends user input
        # --------------------------------------------------

        @self.app.post("/input")
        def input(msg: UserInput):
            logger.info(
                "Received frontend input: role=%s content=%r",
                msg.role,
                msg.content,
            )
            turn = {
                "role": "system",
                "content": "Input received. Processing is not implemented yet.",
            }
            self._publish_turn(turn)

            return turn

        @self.app.get("/events")
        def events():
            subscriber: queue.Queue[dict[str, str]] = queue.Queue(maxsize=100)
            self.subscribers.add(subscriber)

            def stream():
                try:
                    for turn in self.turns:
                        yield f"data: {json.dumps(turn)}\n\n"

                    while True:
                        try:
                            turn = subscriber.get(timeout=15)
                            yield f"data: {json.dumps(turn)}\n\n"
                        except queue.Empty:
                            yield ": keepalive\n\n"
                finally:
                    self.subscribers.discard(subscriber)

            return StreamingResponse(
                stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

        # --------------------------------------------------
        # SPA fallback
        # --------------------------------------------------

        @self.app.get("/{path:path}")
        def spa(path: str):
            return FileResponse(
                self.web_dir / "index.html",
                headers={"Cache-Control": "no-store"},
            )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def serve(
        self,
        host: str = "0.0.0.0",
        port: int = 8100,
        reload: bool = False,
    ):

        import uvicorn

        uvicorn.run(
            self.app,
            host=host,
            port=port,
            reload=reload,
            access_log=False,
            log_config=None,
        )

    def start(
        self,
        host: str = "0.0.0.0",
        port: int = 8100,
    ):

        thread = threading.Thread(
            target=self.serve,
            kwargs={
                "host": host,
                "port": port,
                "reload": False,
            },
            daemon=True,
        )

        thread.start()

        return thread


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if __name__ == "__main__":

    import argparse

    from rich.console import Console
    from rich.logging import RichHandler

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            RichHandler(
                console=Console(),
                rich_tracebacks=True,
            )
        ],
    )

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8100
    )

    parser.add_argument(
        "--director",
        type=str,
        default="http://localhost:8000",
    )

    args = parser.parse_args()

    frontend_actor = FrontendActor(
        name="Frontend Actor",
        director_url=args.director,
        description="Browser frontend bridge",
    )

    frontend_actor.serve(
        host=args.host,
        port=args.port,
    )
