from aidu.ai.actor.actor import RunRequest


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
            "session_context": {"domain": "atomic-structure"},
            "applet_input": {
                "applet": "applet-periodic-table",
                "infoStore": {"elementName": "Lithium"},
            },
        },
    )

    assert req.message.kind == "applet"
    assert req.info.summary == "chemistry turn"
    assert req.info.session_context == {"domain": "atomic-structure"}
    assert req.message.content == "Applet event: applet-periodic-table"
    assert req.info.applet_input == {
        "applet": "applet-periodic-table",
        "infoStore": {"elementName": "Lithium"},
    }
