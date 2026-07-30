# Copyright (C) 2026 Dr. Wolfgang Spahn, PHBern
#
# MIT License — see LICENSE file for details.
# If you use this software in academic work, citation of the original author is requested.
"""Expose an agent workflow through a small REST service.

Role
----
The actor is the HTTP boundary in front of an AIDu ``Controller`` and its
agents. It consumes a ``RunRequest`` containing the current user/applet
message plus session context and recent dialog history. It converts the
message into an initial artifact, builds the shared workflow context, and asks
the controller to chain that artifact through the configured agents.

The synchronous ``POST /run`` route returns the latest display text together
with optional applet commands, activity lifecycle events, student belief, and
teacher-target-derived knowledge progress. ``POST /run/stream`` runs the same
workflow but sends text deltas followed by the same final response as NDJSON.

Example request::

    curl -X POST "http://localhost:8000/run" \\
      -H "Content-Type: application/json" \\
      -d '{
        "message": {
          "role": "user",
          "content": "Hello",
          "actor": "math_student"
        },
        "info": {
          "summary": "Test run",
          "messages": [{"role": "user", "content": "Hello"}],
          "session_context": {"on_air": true}
        }
      }'

Representative response::

    {
      "role": "math_tutor",
      "content": "Hello! What would you like to work on?",
      "backend_belief_state": {
        "engagement": 0.8,
        "confidence": 0.5
      },
      "backend_knowledge_progress_state": {
        "teacher-target-id": {
          "mastery": 0.4,
          "positive_evidence": 2.0,
          "negative_evidence": 3.0
        }
      }
    }

Only ``role`` and ``content`` are always present in the response; state,
commands, and events are included when the workflow produces them.
"""

from aidu.ai.actor.turn_scope import JoinEndAgent, TurnSideTasks, get_turn_side_tasks

__all__ = [
    "JoinEndAgent",
    "TurnSideTasks",
    "get_turn_side_tasks",
]
