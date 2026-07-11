# Copyright (C) 2026 Dr. Wolfgang Spahn, PHBern
#
# MIT License — see LICENSE file for details.
# If you use this software in academic work, citation of the original author is requested.
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
from aidu.ai.core.artifacts import AppletArtifact, Artifact, ArtifactType, TextArtifact
from aidu.ai.core.context import Context, Message
from aidu.ai.archetype.archetype import archetype_dict

logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

PROGRESS_TARGET_ALIASES = {
    "atomic-particles": "neutron-identity",
}
PROGRESS_META_KEYS = {
    "progress_update_count",
    "progress_update_indicator",
}


def _canonical_progress_target_id(target_id: str) -> str:
    return PROGRESS_TARGET_ALIASES.get(target_id, target_id)

# console = Console()


def _is_applet_command_artifact(artifact: Artifact) -> bool:
    """Return True when an applet artifact is an outbound command."""
    if not isinstance(artifact, AppletArtifact):
        return False

    content = artifact.content
    return bool(content.get("applet") and content.get("command"))


def _activity_event_from_artifact(artifact: Artifact) -> dict[str, Any] | None:
    """Return a frontend activity event carried by a structured artifact."""
    if getattr(artifact, "type", "") != "json":
        return None

    content = artifact.content
    if not isinstance(content, dict):
        return None

    event_type = str(content.get("type") or "")
    if event_type != "ai_activity_finalized":
        return None

    return content


def _display_artifact_from_artifacts(artifacts: list[Artifact]) -> Artifact | None:
    """Return the latest artifact that should be shown as assistant text."""
    return next(
        (
            artifact
            for artifact in reversed(artifacts)
            if isinstance(artifact, TextArtifact) and isinstance(artifact.content, str)
        ),
        None,
    )


def _normalize_student_progress(student_progress: Any) -> dict[str, float]:
    """Return progress as ``target_id -> numeric progress``."""
    if student_progress is None:
        return {}

    if hasattr(student_progress, "model_dump"):
        student_progress = student_progress.model_dump(mode="json")

    if not isinstance(student_progress, dict):
        return {}

    # Legacy shape: {"targets": [{"id": "...", "mastery": 0.0}, ...], ...}
    targets = student_progress.get("targets")
    if isinstance(targets, list):
        progress_by_target: dict[str, float] = {}
        for target in targets:
            if not isinstance(target, dict):
                continue
            target_id = str(target.get("id") or "").strip()
            if not target_id or target_id in PROGRESS_META_KEYS:
                continue
            mastery = target.get("mastery")
            progress_by_target[_canonical_progress_target_id(target_id)] = float(mastery) if isinstance(mastery, (int, float)) else 0.0
        return progress_by_target

    # Current/expected shape: {"target-id": 0.0, ...}
    normalized: dict[str, float] = {}
    for key, value in student_progress.items():
        target_id = str(key)
        if target_id in PROGRESS_META_KEYS:
            continue
        if isinstance(value, (int, float)):
            normalized[_canonical_progress_target_id(target_id)] = float(value)
    return normalized


# curl \
#  -X POST "http://localhost:8000/run" -H "Content-Type: application/json" \
#  -d '{"message": {"role": "user", "content": "Hello", "actor": "math_student"}, "info": {"summary": "Test run", "messages": [{"role": "user", "content": "Hello"}]}}'


class RunInfo(BaseModel):
    """Run-level information that is not part of the current message."""

    summary: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None
    session_context: dict[str, Any] = Field(default_factory=dict)
    applet_input: dict[str, Any] | None = None


class RunRequest(BaseModel):
    """Request sent to an actor service.

    ``message`` is the current actor-style message. Fields such as ``role``,
    ``content``, ``actor``, and ``kind`` belong there.

    ``info`` carries run metadata that helps the actor build context, such as
    dialog history, session context, and structured applet input.
    """

    message: Message = Field(default_factory=Message)
    info: RunInfo = Field(default_factory=RunInfo)


class Actor:
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
    # API
    # ------------------------------------------------------------------

    def build_context_from_request(self, req: RunRequest) -> Context:
        context = Context()
        context.create_agent_states(self.agents)

        # populate context with request data
        # ...
        return context

    def startup_from_request(self, req: RunRequest, context: Context) -> type[Agent]:
        """Return the agent class that should handle this request first."""
        return self.startup

    def build_artifact_from_request(self, req: RunRequest, context: Context) -> Artifact:
        """Build the first workflow artifact from a frontend/director request."""
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
                "agents": [agent.__class__.__name__ for agent in self.agents],
                "startup": self.startup.__name__,
                "routing": "dynamic" if self.__class__.startup_from_request is not Actor.startup_from_request else "static",
            }

        @self.app.post("/run")
        def run(req: RunRequest):
            content = str(req.message.content or "")
            context = self.build_context_from_request(req)
            startup = self.startup_from_request(req, context)
            logger.warning(
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

            logger.debug(f"Run completed with final context: {context}")

            artifacts = list(context.artifacts.values())
            final_artifact = artifacts[-1] if artifacts else None
            display_artifact = _display_artifact_from_artifacts(artifacts)
            applet_command_artifact = next(
                (
                    artifact
                    for artifact in reversed(artifacts)
                    if _is_applet_command_artifact(artifact)
                ),
                None,
            )
            activity_event = next(
                (
                    event
                    for artifact in reversed(artifacts)
                    if (event := _activity_event_from_artifact(artifact))
                ),
                None,
            )

            response_artifact = display_artifact or final_artifact
            response = {
                "role": (response_artifact.producer if response_artifact else None),
                "content": (response_artifact.content if response_artifact else None),
            }
            student_belief = context.state.data.get("StudentBelief")
            if student_belief is not None:
                response["backend_belief_state"] = (
                    student_belief.model_dump(mode="json")
                    if hasattr(student_belief, "model_dump")
                    else student_belief
                )
            student_progress = context.state.data.get("StudentProgress")
            normalized_progress = _normalize_student_progress(student_progress)
            if normalized_progress:
                response["backend_progress_state"] = normalized_progress
                logger.warning(
                    "Actor response includes backend_progress_state keys=%s nonzero=%s",
                    sorted(normalized_progress.keys()),
                    {key: value for key, value in normalized_progress.items() if value},
                )

            if applet_command_artifact:
                response["applet"] = applet_command_artifact.content.get("applet")
                response["applet_command"] = applet_command_artifact.content.get("command")
                if final_artifact is applet_command_artifact:
                    response["content"] = ""

            if activity_event:
                response["activity_event"] = activity_event
                logger.info("Actor response includes activity_event=%s", activity_event)
                if display_artifact is None and final_artifact is not None and _activity_event_from_artifact(final_artifact):
                    response["content"] = ""

            return response

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
