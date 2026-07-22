# Copyright (C) 2026 Dr. Wolfgang Spahn, PHBern
#
# MIT License — see LICENSE file for details.
# If you use this software in academic work, citation of the original author is requested.
from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aidu.ai.core.agent_result import AgentResult
from aidu.ai.core.context import Context
from aidu.ai.llm.agent import EndAgent

logger = logging.getLogger(__name__)

SIDE_TASKS_KEY = "turn_side_tasks"
SideResultHandler = Callable[[Any, Context], None]
SideTaskCallable = Callable[[], Any]


@dataclass
class TurnSideTasks:
    """Turn-scoped side-task collector with an explicit join point.

    The controller deep-copies ``Context`` between agents. This object is a
    shared handle on purpose, so deep copies of the context keep referring to
    the same side-task group for the current turn.
    """

    executor: concurrent.futures.ThreadPoolExecutor = field(
        default_factory=lambda: concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="aidu-turn-side",
        )
    )
    tasks: list[tuple[str, concurrent.futures.Future, SideResultHandler | None]] = field(default_factory=list)

    def __deepcopy__(self, memo):
        return self

    def spawn(self, name: str, fn: SideTaskCallable, on_result: SideResultHandler | None = None) -> None:
        logger.debug("Turn side task spawned: %s", name)
        self.tasks.append((name, self.executor.submit(fn), on_result))

    def join(self, context: Context) -> None:
        try:
            if self.tasks:
                logger.info("Joining %s turn side task(s).", len(self.tasks))
            for name, future, on_result in self.tasks:
                try:
                    result = future.result()
                    logger.debug("Turn side task completed: %s", name)
                    if on_result is not None:
                        on_result(result, context)
                except Exception:
                    logger.exception("Turn side task failed: %s", name)
        finally:
            self.tasks.clear()
            self.executor.shutdown(wait=True, cancel_futures=False)


def get_turn_side_tasks(context: Context) -> TurnSideTasks:
    side = context.control.data.get(SIDE_TASKS_KEY)
    if not isinstance(side, TurnSideTasks):
        side = TurnSideTasks()
        context.control.data[SIDE_TASKS_KEY] = side
    return side


class JoinEndAgent(EndAgent):
    """End agent that joins turn side effects before the actor response is built."""

    def run(self, artifact, context: Context, agents=None) -> tuple[AgentResult, Context]:
        side = context.control.data.pop(SIDE_TASKS_KEY, None)
        if isinstance(side, TurnSideTasks):
            side.join(context)
        return super().run(artifact=artifact, context=context, agents=agents)
