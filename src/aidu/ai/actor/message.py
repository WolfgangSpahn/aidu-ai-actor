from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from aidu.ai.core.artifacts import Artifact
from aidu.ai.core.context import Context


class ActorMessage(BaseModel):
    id: str
    type: Literal["request", "result", "status", "error"]
    sender: str | None = None
    target: str
    processor: str | None = None
    artifact: Artifact | None = None
    context: Context | None = None
    data: dict[str, Any] = Field(default_factory=dict)