# src/aidu/ai/actor/actor.py

from __future__ import annotations
import logging
import json
from collections import deque
import threading
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from rich.console import Console

from aidu.ai.actor.config import config
from aidu.ai.controller.controller import Controller
from aidu.ai.core.artifacts import ArtifactType, TextArtifact
from aidu.ai.core.context import Context


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console = Console()

class RunRequest(BaseModel):
    role: str
    content: str


class Actor:
    def __init__(
        self,
        name: str,
        processors: dict[str, Processor],
        startup: str,
        context: Context | None = None,
        show_trace: bool = False,
        description: str = "",
    ):
        self.name = name
        self.startup = startup
        self.context = context or Context()
        self.description = description
        self.controller = Controller(f"Controller of {name}", context=self.context, processors=processors, show_trace=show_trace)

        self.app = FastAPI(
            title=name,
            description=description,
        )

        self._register_routes()

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

            artifact = TextArtifact(
                producer=req.role,
                step=0,
                content=req.content,
            )

            config.max_step = 10

            context =self.controller.run(
                start=self.startup,
                artifact=artifact,
                max_step=config.max_step,
                console=console,
            )

            logger.debug(f"Run completed with final context: {context}")
            final_artifact = list(context.artifacts.items())[-1][1] if context.artifacts else None

            return {
                "role": final_artifact.producer if final_artifact else None,
                "content": final_artifact.content if final_artifact else None,
            }

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
            access_log=False,
            log_config=None
        )

    def start(self, host="0.0.0.0", port=8000):

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

if __name__ == "__main__":
    import argparse

    from aidu.ai.agents.math_tutor import MathTutor
    from aidu.ai.agents.chat_bot import ChatBot
    from aidu.ai.agents.symbolic_solver import SymbolicSolver
    from aidu.ai.llm.clients.openai import OpenAIClient
    from aidu.ai.controller.processor import DummyProcessor, EchoProcessor, Processor, UserInputProcessor, AgentProcessor

    parser = argparse.ArgumentParser()
    parser.add_argument("--actor", type=str, default="math_tutor", choices=["math_tutor", "user_input"])
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", type=bool, default=False)
    args = parser.parse_args()

    # Set up the actor with a demo controller and processors

    client = OpenAIClient(model="gpt-4o-mini")

    if args.actor == "math_tutor":

        math_tutor_actor = Actor(
            name="Demo Math Tutor Actor",
            processors={
                "input": UserInputProcessor(target="math_tutor"),
                "math_tutor": AgentProcessor(MathTutor(client)),
                "symbolic_solver": AgentProcessor(SymbolicSolver()),
            },
            startup="input",
            show_trace=True,
            description="A demo math tutor actor for testing purposes.",
        )

        # Start the actor server
        math_tutor_actor.serve(
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.actor == "user_input":

        user_input_actor = Actor(
            name="Demo User Input Actor",
            processors={
                "input": UserInputProcessor(target="exit"),
                "echo": EchoProcessor(),
            },
            startup="input",
            show_trace=True,
            description="A demo user input actor that echoes back input.",
        )

        # Start the actor server
        user_input_actor.serve(
            host=args.host,
            port=args.port,
            reload=args.reload,
        )