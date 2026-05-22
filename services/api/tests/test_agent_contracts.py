import pytest
from pydantic import ValidationError

from api.agent_contracts import (
    AgentResultStreamEvent,
    MessageRequest,
    TextContentBlock,
)


def test_message_request_accepts_typed_input_parts():
    request = MessageRequest.model_validate(
        {
            "thread_key": "thread-1",
            "assignment_generation": 4,
            "parts": [{"type": "text", "text": "hello"}],
        }
    )

    assert request.parts == [TextContentBlock(type="text", text="hello")]


def test_message_request_rejects_untyped_or_output_only_content():
    with pytest.raises(ValidationError):
        MessageRequest.model_validate(
            {
                "thread_key": "thread-1",
                "assignment_generation": 4,
                "event": {
                    "type": "user",
                    "message": {"role": "user", "content": "hello"},
                },
            }
        )

    with pytest.raises(ValidationError):
        MessageRequest.model_validate(
            {
                "thread_key": "thread-1",
                "assignment_generation": 4,
                "parts": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "not valid user input",
                    }
                ],
            }
        )


def test_result_stream_event_result_must_be_text():
    event = AgentResultStreamEvent.model_validate({"type": "result", "result": "done"})

    assert event.result == "done"

    with pytest.raises(ValidationError):
        AgentResultStreamEvent.model_validate(
            {"type": "result", "result": {"text": "ambiguous shape"}}
        )
