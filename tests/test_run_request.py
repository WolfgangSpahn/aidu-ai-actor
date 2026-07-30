import pytest
from pydantic import ValidationError

from aidu.ai.actor.types import RunRequest


def test_run_request_uses_nested_message_and_info():
    req = RunRequest(
        message={
            "role": "user",
            "content": "Applet event: applet-periodic-table",
            "actor": "gui_user_actor",
            "kind": "applet",
        },
        info={
            "summary": "chemistry turn",
            "messages": [{"role": "user", "content": "hi"}],
            "session_id": "session-1",
            "session_context": {"on_air": False, "domain": "atomic-structure"},
            "applet_input": {
                "applet": "applet-periodic-table",
                "infoStore": {"elementName": "Lithium"},
            },
        },
    )

    assert req.message.kind == "applet"
    assert req.info.summary == "chemistry turn"
    assert req.info.session_context.on_air is False
    assert req.info.session_context.domain == "atomic-structure"
    assert req.message.content == "Applet event: applet-periodic-table"
    assert req.info.applet_input == {
        "applet": "applet-periodic-table",
        "infoStore": {"elementName": "Lithium"},
    }


def test_run_request_requires_backend_on_air_decision():
    with pytest.raises(ValidationError, match="on_air"):
        RunRequest(
            message={"role": "user", "content": "Hello"},
            info={"session_context": {"domain": "atomic-structure"}},
        )
