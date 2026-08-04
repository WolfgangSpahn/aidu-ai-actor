# Copyright (C) 2026 Dr. Wolfgang Spahn, PHBern
#
# MIT License — see LICENSE file for details.
# If you use this software in academic work, citation of the original author is requested.

"""
Implement the REST-facing actor that builds context and runs agent workflows.

This module registers run routes, delegates each request to a ``Controller``,
and converts the resulting artifacts and state into the HTTP response.
"""

from __future__ import annotations
import logging
import json


from collections import deque
from multiprocessing import context
from queue import Queue
import threading
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from rich.console import Console
from rich.logging import RichHandler

from aidu.ai.llm.agent import Agent, EndAgent
from aidu.ai.actor.config import config
from aidu.ai.controller.controller import Controller
from aidu.ai.core.artifacts import (
    ActivityEventArtifact,
    AppletArtifact,
    Artifact,
    TextArtifact,
    latest_display_artifact,
)
from aidu.ai.core.context import Context
from aidu.ai.archetype.archetype import archetype_dict
from aidu.ai.core.knowledge_progress import StudentKnowledgeProgress
from aidu.ai.actor.types import RunRequest

logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

# console = Console()


class Actor:
    """Run an agent workflow behind a small FastAPI service.

    The HTTP routes call :meth:`execute_run`, which applies a sequence of
    overridable request-lifecycle hooks before handing the resulting artifact
    and context to the controller. Subclasses normally customize context
    construction, startup-agent selection, or request-artifact construction;
    they do not register a separate route for those hooks.
    """

    def __init__(
        self,
        name: str,
        agents: list[Agent],
        startup: type[Agent],
        description: str = "",
        avatar: str | None = None,
        console: Console | None = None,
    ):
        self.id = str(uuid4())
        self.name = name
        self.avatar = avatar or name
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
    # Request lifecycle hooks
    # ------------------------------------------------------------------

    def build_context_from_request(self, req: RunRequest) -> Context:
        """Build the workflow context used for one ``RunRequest``.

        This is an overridable helper hook, not an HTTP route. ``execute_run``
        invokes it for both ``POST /run`` and ``POST /run/stream``. The base
        implementation applies common request configuration and initializes
        agent state; specialized actors may add session context, dialog
        history, student belief, and teacher-target-derived progress.
        """
        context = Context()
        self.configure_context_from_request(context, req)
        context.create_agent_states(self.agents)

        # populate context with request data
        # ...
        return context

    def configure_context_from_request(self, context: Context, req: RunRequest) -> None:
        """Copy the backend's provider-access decision into the workflow context."""
        context.on_air = req.info.session_context.on_air

    def startup_from_request(self, req: RunRequest, context: Context) -> type[Agent]:
        """Return the agent class that should handle this request first."""
        return self.startup

    def build_artifact_from_request(self, req: RunRequest, context: Context) -> Artifact:
        """Convert the request message into the controller's initial artifact.

        This is another overridable lifecycle hook called by ``execute_run``;
        it is not itself registered as an HTTP route.
        """
        role = str(req.message.role or "user")
        content = str(req.message.content or "")
        applet_input = req.info.applet_input

        if req.message.kind == "applet":
            return AppletArtifact(
                producer=role,
                step=0,
                content=applet_input if isinstance(applet_input, dict) else {"raw": content},
            )

        return TextArtifact(
            producer=role,
            step=0,
            content=content,
        )

    def execute_run(self, req: RunRequest, stream_callback=None) -> dict[str, Any]:
        """Execute one actor turn, optionally reporting provider text deltas."""
        content = str(req.message.content or "")
        context = self.build_context_from_request(req)
        if stream_callback is not None:
            context.control.data["stream_callback"] = stream_callback
        startup = self.startup_from_request(req, context)
        logger.debug(
            "Actor run name=%s startup=%s default_startup=%s content_prefix=%r",
            self.name,
            startup.__name__,
            self.startup.__name__,
            content[:240],
        )
        artifact = self.build_artifact_from_request(req, context)
        config.max_step = 10
        context = self.controller.run(
            start=startup,
            artifact=artifact,
            mailbox=deque(),
            context=context,
            max_step=config.max_step,
            console=self.console,
        )

        artifacts = list(context.artifacts.values())
        final_artifact = artifacts[-1] if artifacts else None
        display_artifact = latest_display_artifact(artifacts)
        applet_command_artifact = next(
            (artifact for artifact in reversed(artifacts) if isinstance(artifact, AppletArtifact) and artifact.is_outbound_command()),
            None,
        )
        activity_event = next(
            (artifact.content for artifact in reversed(artifacts) if isinstance(artifact, ActivityEventArtifact)),
            None,
        )
        response_artifact = display_artifact or final_artifact
        response: dict[str, Any] = {
            "role": response_artifact.producer if response_artifact else None,
            "content": response_artifact.content if response_artifact else None,
        }
        student_belief = context.state.data.get("StudentBelief")
        if student_belief is not None:
            response["backend_belief_state"] = student_belief.model_dump(mode="json") if hasattr(student_belief, "model_dump") else student_belief
        student_knowledge_progress: StudentKnowledgeProgress | None = (
            context.state.data.get("StudentKnowledgeProgress")
        )
        if student_knowledge_progress is not None:
            response["backend_knowledge_progress_state"] = (
                student_knowledge_progress.clamped().model_dump(mode="json")
            )
        supervisor_state = context.state.data.get("SupervisorState")
        if supervisor_state is not None and context.control.data.get("emit_supervision_state", True):
            response["backend_supervision_state"] = supervisor_state.model_dump(mode="json") if hasattr(supervisor_state, "model_dump") else supervisor_state
        if applet_command_artifact:
            response["applet"] = applet_command_artifact.content.get("applet")
            response["applet_command"] = applet_command_artifact.content.get("command")
            if final_artifact is applet_command_artifact:
                response["content"] = ""
        if activity_event:
            response["activity_event"] = activity_event
            if display_artifact is None and isinstance(final_artifact, ActivityEventArtifact):
                response["content"] = ""
        return response

    # ------------------------------------------------------------------
    # FastAPI route registration
    # ------------------------------------------------------------------

    def _register_routes(self):
        """Register health, metadata, synchronous-run, and streaming-run routes."""

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
                "agents": [agent.__class__.__name__ for agent in self.agents],
                "startup": self.startup.__name__,
                "routing": "dynamic" if self.__class__.startup_from_request is not Actor.startup_from_request else "static",
            }

        @self.app.post("/run")
        def run(req: RunRequest):
            return self.execute_run(req)

        @self.app.post("/run/stream")
        def run_stream(req: RunRequest):
            def generate():
                events: Queue = Queue()

                def execute() -> None:
                    try:
                        response = self.execute_run(
                            req,
                            stream_callback=lambda delta: events.put({"type": "delta", "content": delta}),
                        )
                        events.put({"type": "final", "response": response})
                    except Exception as exc:
                        logger.exception("Streaming actor run failed")
                        events.put({"type": "error", "error": str(exc)})
                    finally:
                        events.put(None)

                threading.Thread(target=execute, daemon=True).start()
                while True:
                    event = events.get()
                    if event is None:
                        break
                    yield json.dumps(event, default=str) + "\n"

            return StreamingResponse(generate(), media_type="application/x-ndjson")

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
            #                     "student_knowledge_progress": "So far student guessed 3 without any reasoning, you asked to try again.",
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
