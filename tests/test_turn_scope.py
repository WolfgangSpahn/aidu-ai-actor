from aidu.ai.actor.turn_scope import JoinEndAgent
from aidu.ai.core.artifacts import AppletArtifact
from aidu.ai.core.context import Context


def test_join_end_agent_preserves_structured_artifact():
    artifact = AppletArtifact(
        producer="tutor",
        step=1,
        content={
            "applet": "applet-build-an-atom",
            "command": {"kind": "set_atom", "protons": 4},
        },
    )

    result, _ = JoinEndAgent().run(artifact, Context())

    assert result.artifacts == [artifact]
    assert result.artifacts[0].content == artifact.content
