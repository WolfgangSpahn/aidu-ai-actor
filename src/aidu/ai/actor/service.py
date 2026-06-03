from __future__ import annotations

from collections import deque
from typing import Any

from aidu.ai.actor.message import ActorMessage
from aidu.ai.controller.controller import Controller


class ActorService:
    def __init__(self, actor_id: str, controller: Controller, processors: dict[str, Any]):
        self.actor_id = actor_id
        self.controller = controller
        self.processors = processors
        self.outbox = deque()

    def receive(self, msg: ActorMessage) -> ActorMessage:
        if msg.artifact is None:
            return ActorMessage(
                id=msg.id,
                type="error",
                sender=self.actor_id,
                target=msg.sender or "director",
                data={"error": "message has no artifact"},
            )

        start = msg.processor or "input"

        context = self.controller.run(
            processors=self.processors,
            start=start,
            artifact=msg.artifact,
            max_step=msg.data.get("max_step", 10),
        )

        result = ActorMessage(
            id=msg.id,
            type="result",
            sender=self.actor_id,
            target=msg.sender or "director",
            context=context,
            data={"step": context.step},
        )

        self.outbox.append(result)
        return result