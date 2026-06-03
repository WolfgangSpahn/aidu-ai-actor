# src/aidu/ai/actor/actor.py

from __future__ import annotations

import json
from collections import deque
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from aidu.ai.controller.controller import Controller


class RunRequest(BaseModel):
    start: str
    artifact: dict[str, Any]
    max_step: int = 20


class Actor:

    def __init__(
        self,
        name: str,
        controller: Controller,
        description: str = "",
    ):
        self.name = name
        self.description = description
        self.controller = controller

        self.events = deque(maxlen=1000)

        self.app = FastAPI(
            title=name,
            description=description,
        )

        self._register_routes()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def emit(self, event: dict):

        self.events.append(event)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def _register_routes(self):

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
                "processors": list(self.controller.processors.keys()),
            }

        @self.app.post("/run")
        def run(req: RunRequest):

            self.emit(
                {
                    "type": "run_started",
                    "start": req.start,
                }
            )

            artifact = self.controller.context.artifacts.model_validate(
                req.artifact
            )

            self.controller.run(
                start=req.start,
                artifact=artifact,
                max_step=req.max_step,
            )

            self.emit(
                {
                    "type": "run_finished",
                }
            )

            return {
                "status": "ok",
            }

        @self.app.get("/events")
        def events():

            def stream():

                last = 0

                while True:

                    while last < len(self.events):

                        event = self.events[last]
                        last += 1

                        yield (
                            f"data: {json.dumps(event)}\n\n"
                        )

            return StreamingResponse(
                stream(),
                media_type="text/event-stream",
            )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def serve(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        reload: bool = False,
    ):

        import uvicorn

        uvicorn.run(
            self.app,
            host=host,
            port=port,
            reload=reload,
        )