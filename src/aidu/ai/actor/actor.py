# src/aidu/ai/actor/actor.py

from __future__ import annotations
import logging
import json


from collections import deque
from multiprocessing import context
import threading
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from rich.console import Console
from rich.logging import RichHandler

from aidu.ai.llm.agent import Agent, EndAgent
from aidu.ai.actor.config import config
from aidu.ai.controller.controller import Controller
from aidu.ai.core.artifacts import ArtifactType, TextArtifact
from aidu.ai.core.context import Context, Message
from aidu.ai.archetype.archetype import archetype_dict

logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

# console = Console()


# curl \
#  -X POST "http://localhost:8000/run" -H "Content-Type: application/json" \
#  -d '{"summary": "Test run", "messages": [{"role": "user", "content": "Hello"}], "actor": "math_student", "role": "user", "content": "Hello"}'


class RunRequest(BaseModel):
    summary: str
    messages: list[Message]
    actor: str
    role: str
    content: str


class Actor:
    def __init__(
        self,
        name: str,
        agents: list[Agent],
        startup: type[Agent],
        description: str = "",
        console: Console | None = None,
    ):
        self.id = str(uuid4())
        self.name = name
        self.startup = startup
        self.console = console

        self.description = description
        self.agents = agents
        self.controller = Controller(
            f"Controller of {name}",
            agents=self.agents,
        )
        self.app = FastAPI(
            title=name,
            description=description,
        )

        self._register_routes()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def build_context_from_request(self, req: RunRequest) -> Context:
        context = Context()
        context.create_agent_states(self.agents)

        # populate context with request data
        # ...
        return context

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
                "agents": [agent.__name__ for agent in self.controller.agents.keys()],
                "startup": self.startup.__name__,
            }

        @self.app.post("/run")
        def run(req: RunRequest):
            context = self.build_context_from_request(req)

            artifact = TextArtifact(
                producer=req.role,
                step=0,
                content=req.content,
            )

            config.max_step = 10

            context = self.controller.run(
                start=self.startup,
                artifact=artifact,
                mailbox=deque(),
                context=context,
                max_step=config.max_step,
                console=self.console,
            )

            logger.debug(f"Run completed with final context: {context}")

            final_artifact = list(context.artifacts.items())[-1][1] if context.artifacts else None

            return {
                "role": (final_artifact.producer if final_artifact else None),
                "content": (final_artifact.content if final_artifact else None),
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

        uvicorn.run(self.app, host=host, port=port, reload=reload, access_log=False, log_config=None)

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


def get_recommendation_data(agents):

    rows = []

    for agent in agents:
        rows.append(
            {
                "source": agent.__class__.__name__,
                "function": "direct",
                "mode": "default",
                "target": agent.target.__name__ if hasattr(agent, "target") and agent.target else None,
                "continuations": [c.__name__ for c in agent.continuations] if hasattr(agent, "continuations") else [],
            }
        )

        if hasattr(agent, "discovered_fn_routes"):
            logger.debug(f"Inspecting agent {agent.__class__.__name__} for discovered routes")
            for fn_name, mode, target, cont in agent.discovered_fn_routes:
                logger.debug(f"Found route in {agent.__class__.__name__}: function {fn_name} targets {target.__name__} with continuations {[c.__name__ for c in cont]}")

                rows.append(
                    {
                        "source": agent.__class__.__name__,
                        "function": fn_name,
                        "mode": mode,
                        "target": target.__name__,
                        "continuations": [c.__name__ for c in cont],
                    }
                )

    return rows


if __name__ == "__main__":
    import argparse

    from aidu.ai.core.belief import StudentBelief

    # from aidu.ai.agents.math_tutor import MathTutor
    from aidu.ai.agents.math_student import MathStudent
    from aidu.ai.agents.chat_bot import ChatBot
    from aidu.ai.agents.symbolic_solver import SymbolicSolver
    from aidu.ai.llm.clients.openai import OpenAIClient
    from aidu.ai.agents.math_tutor import MathUserInput, MathTutor
    from aidu.ai.agents.symbolic_solver import SymbolicSolver

    # ----------------------------------------------------------------------
    # setup rich logging
    # ----------------------------------------------------------------------
    console = Console()

    logging.basicConfig(level=logging.INFO, format="%(message)s - %(funcName)s", handlers=[RichHandler(console=console)])

    parser = argparse.ArgumentParser()
    parser.add_argument("--actor", type=str, default="math_tutor", choices=["math_tutor", "user_input"])
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", type=bool, default=False)
    args = parser.parse_args()

    # Set up the actor with a demo controller and processors

    client = OpenAIClient(model="gpt-5-mini")

    context = Context()

    # Initialize belief state
    belief = StudentBelief(  # confused_but_motivated
        engagement=0.90, confidence=0.20, confusion=0.95, frustration=0.30, curiosity=0.80, self_explanation=0.40, guessing=0.20, help_seeking=0.90
    )

    context.state.data["StudentBelief"] = belief

    if args.actor == "math_tutor":
        logger.info("Starting Math Tutor Actor...")

        agents = [
            # MathTutor(client, prompt_args={"tutor_name": "Alice",
            #                     "focus_area": "general math",
            #                     "history": "Student had been asked to solve the equation x**2 - 4 = 0.",
            #                     "student_progress": "So far student guessed 3 without any reasoning, you asked to try again.",
            #                     "level"     : "beginner"}),
            MathStudent(
                client,
                archetype_dict["balanced_student"],
                archetype_dict["learned_helplessness"],
                0.1,
            ),
            SymbolicSolver(),
            EndAgent(),
        ]

        # test calls to discover function routes and recommendations
        # agents[0].fc_route_symbolic_solver(Context(),problem="solve(x**2 - 4, x)") # should route to SymbolicSolver
        # agents[0].fc_route_symbolic_solver(Context(),problem="hello") # triggers error handling route

        # Initialize state for each agent

        context.create_agent_states(agents)

        MathStudent.agent = EndAgent

        # console.print("Routes",get_recommendation_data(agents))

        math_student_actor = Actor(
            name="Demo Math Student Actor",
            agents=agents,
            startup=MathStudent,
            description="A demo math student actor for testing purposes.",
        )

        # Start the actor server
        math_student_actor.serve(
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
