# Copyright (C) 2026 Dr. Wolfgang Spahn, PHBern
#
# MIT License — see LICENSE file for details.
# If you use this software in academic work, citation of the original author is requested.

"""
Define the validated HTTP request and session-context contracts for actors.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aidu.ai.core.context import Message, Messages
from aidu.ai.core.session import SessionContext


class RunInfo(BaseModel):
    """Supporting session and history data used to prepare one actor run."""

    summary: str = ""
    messages: Messages = Field(default_factory=Messages)
    session_id: str | None = None
    session_context: SessionContext
    applet_input: dict[str, Any] | None = None


class RunRequest(BaseModel):
    """Data consumed by ``Actor.execute_run`` for ``/run`` and ``/run/stream``."""

    message: Message = Field(default_factory=Message)
    info: RunInfo
