"""Typed contracts for the durable agent control-plane API.

This module is the source of truth for the agent HTTP and SSE contracts that
clients build against.  The TypeScript API client generates its public contract
types from these Pydantic/typing definitions.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtensibleContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


AgentMessageRole: TypeAlias = Literal["user", "assistant", "system", "tool"]
AgentExecutionStatus: TypeAlias = Literal[
    "queued",
    "running",
    "retry_wait",
    "cancel_requested",
    "completed",
    "failed_permanent",
    "cancelled",
]
AgentTerminalReason: TypeAlias = Literal[
    "completed",
    "cancel_requested",
    "cancelled",
    "released",
    "harness_error",
    "harness_auth_failed",
    "amp_reconnect_timeout",
    "assignment_missing",
    "execution_error",
    "stream_ended_without_turn_done",
    "hard_deadline_exceeded",
    "silence_deadline_exceeded",
]


class Base64Source(StrictContractModel):
    type: Literal["base64"]
    media_type: str
    data: str


class TextContentBlock(StrictContractModel):
    type: Literal["text"]
    text: str


class BinaryContentBlock(StrictContractModel):
    type: Literal["image", "document", "file"]
    name: str | None = None
    mime_type: str | None = None
    size: int | None = None
    slack_file_id: str | None = None
    source_path: str | None = None
    source: Base64Source


class AttachmentRefContentBlock(StrictContractModel):
    type: Literal["attachment_ref"]
    id: str | None = None
    attachment_id: str | None = None
    name: str
    mime_type: str | None = None
    media_type: str | None = None
    source_path: str | None = None
    source_url: str | None = None


class ToolUseContentBlock(StrictContractModel):
    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any]


class ToolResultContentBlock(StrictContractModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Any = None
    is_error: bool | None = None


AgentInputContentBlock: TypeAlias = Annotated[
    TextContentBlock | BinaryContentBlock | AttachmentRefContentBlock,
    Field(discriminator="type"),
]
AgentContentBlock: TypeAlias = Annotated[
    AgentInputContentBlock | ToolUseContentBlock | ToolResultContentBlock,
    Field(discriminator="type"),
]


class AgentMessagePayload(ExtensibleContractModel):
    role: AgentMessageRole | None = None
    content: list[AgentContentBlock] | str
    usage: dict[str, Any] | None = None
    model: str | None = None


class AgentInputMessagePayload(ExtensibleContractModel):
    role: AgentMessageRole | None = None
    content: list[AgentInputContentBlock]


class AgentMessageEvent(StrictContractModel):
    type: Literal["user", "assistant"]
    message: AgentInputMessagePayload


class AgentDelivery(ExtensibleContractModel):
    platform: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    thread_ts: str | None = None
    recipient_user_id: str | None = None
    recipient_team_id: str | None = None


class SpawnRequest(StrictContractModel):
    thread_key: str
    spawn_id: str | None = None
    harness: str | None = None
    engine: str | None = None
    persona_id: str | None = None
    agents_md_override: str | None = None


class SpawnResult(StrictContractModel):
    ok: bool
    runtime_id: str
    thread_key: str
    trace_id: str | None = None
    assignment_state: str
    assignment_generation: int
    persona_id: str | None = None
    prompt_ref: str | None = None
    effective_agents_md_sha256: str | None = None


class MessageRequest(StrictContractModel):
    thread_key: str
    assignment_generation: int
    message_id: str | None = None
    event: AgentMessageEvent | None = None
    role: AgentMessageRole | None = None
    parts: list[AgentInputContentBlock] | None = None
    user_id: str | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_message_payload(self) -> "MessageRequest":
        if self.event is None and self.parts is None:
            raise ValueError("either event or parts is required")
        return self


class MessageAccepted(StrictContractModel):
    ok: bool
    message_id: str
    stored_event_id: str | None = None
    attachment_ids: list[str]
    idempotent: bool | None = None


class BatchMessageItem(StrictContractModel):
    assignment_generation: int | None = None
    message_id: str | None = None
    event: AgentMessageEvent | None = None
    role: AgentMessageRole | None = None
    parts: list[AgentInputContentBlock] | None = None
    user_id: str | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_message_payload(self) -> "BatchMessageItem":
        if self.event is None and self.parts is None:
            raise ValueError("either event or parts is required")
        return self


class BatchMessageRequest(StrictContractModel):
    thread_key: str
    assignment_generation: int
    message_id: str | None = None
    event: AgentMessageEvent | None = None
    role: AgentMessageRole | None = None
    parts: list[AgentInputContentBlock] | None = None
    user_id: str | None = None
    metadata: dict[str, Any] | None = None
    messages: list[BatchMessageItem] | None = None

    @model_validator(mode="after")
    def validate_message_payload(self) -> "BatchMessageRequest":
        if self.messages is None and self.event is None and self.parts is None:
            raise ValueError("either messages, event, or parts is required")
        return self


class BatchMessageAccepted(StrictContractModel):
    ok: bool
    inserted: int
    message_ids: list[str]


class ExecuteRequest(StrictContractModel):
    thread_key: str
    assignment_generation: int | None = None
    execute_id: str | None = None
    harness: str | None = None
    delivery: AgentDelivery | None = None
    platform: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] | None = None
    message: str | None = None
    engine: str | None = None
    persona_id: str | None = None


class ExecutionAccepted(StrictContractModel):
    ok: bool
    execution_id: str
    execute_id: str
    assignment_generation: int
    status: AgentExecutionStatus
    final_key: str
    delivery_token: str
    idempotent: bool | None = None


class SteerExecutionRequest(StrictContractModel):
    content_blocks: list[AgentInputContentBlock] | None = None
    message_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] | None = None


class AgentRepoContext(StrictContractModel):
    cwd: str | None = None
    repo_owner: str | None = None
    repo_name: str | None = None
    git_ref: str | None = None
    git_commit: str | None = None


class AgentExecutionRecord(ExtensibleContractModel):
    execution_id: str
    thread_key: str
    assignment_generation: int
    execute_id: str
    status: AgentExecutionStatus
    durable_turn_id: str | None = None
    terminal_reason: AgentTerminalReason | None = None
    result_text: str | None = None
    error_text: str | None = None
    agent_thread_id: str
    metadata: dict[str, Any]
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str | None = None


class ThreadExecutionSummary(StrictContractModel):
    execution_id: str
    execute_id: str
    status: AgentExecutionStatus
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ThreadExecutionList(StrictContractModel):
    thread_key: str
    executions: list[ThreadExecutionSummary]


class ExecutionControlResult(StrictContractModel):
    ok: bool
    execution_id: str
    thread_key: str
    status: AgentExecutionStatus | Literal["steered"]
    idempotent: bool | None = None


class ReleaseRequest(StrictContractModel):
    release_id: str | None = None
    cancel_inflight: bool = False


class ReleaseThreadResultReleased(StrictContractModel):
    ok: Literal[True]
    thread_key: str
    released: Literal[True]
    assignment_generation: int
    runtime_id: str


class ReleaseThreadResultNotReleased(StrictContractModel):
    ok: Literal[True]
    thread_key: str
    released: Literal[False]
    reason: str


ReleaseThreadResult: TypeAlias = Annotated[
    ReleaseThreadResultReleased | ReleaseThreadResultNotReleased,
    Field(discriminator="released"),
]


class AgentStatusActiveAssignment(StrictContractModel):
    assignment_generation: int
    runtime_id: str
    harness: str
    persona_id: str | None = None
    prompt_ref: str | None = None
    effective_agents_md_sha256: str | None = None
    state: str


class AgentStatus(ExtensibleContractModel):
    thread_key: str | None = None
    state: str | None = None
    harness: str | None = None
    engine: str | None = None
    pending_messages: int | None = None
    last_result: str | None = None
    active_assignment: AgentStatusActiveAssignment | None = None


class FinalDeliveryPayload(ExtensibleContractModel):
    execution_id: str | None = None
    thread_key: str | None = None
    status: AgentExecutionStatus | None = None
    terminal_reason: AgentTerminalReason | None = None
    session_title: str | None = None
    session_header: str | None = None
    result_text: str | None = None
    result: str | None = None
    text: str | None = None
    final_text: str | None = None
    message: str | None = None
    error_text: str | None = None
    slackbot_streamed_answer_chars: int | None = None
    agent_thread_id: str | None = None
    repo_context: AgentRepoContext | None = None
    suppress_final_delivery: bool | None = None


class FinalDeliveryRecord(StrictContractModel):
    execution_id: str
    thread_key: str
    trace_id: str | None = None
    traceparent: str | None = None
    attempt_count: int
    delivery: AgentDelivery | None = None
    final_payload: FinalDeliveryPayload | None = None


class FinalDeliveryClaimResponse(StrictContractModel):
    deliveries: list[FinalDeliveryRecord]


class FinalDeliveryMutationResult(StrictContractModel):
    ok: bool
    execution_id: str
    idempotent: bool | None = None


class ClaimFinalDeliveryRequest(StrictContractModel):
    consumer_id: str
    limit: int = 1
    lease_seconds: int = 60
    platform: str | None = None


class RenewFinalDeliveryLeaseRequest(StrictContractModel):
    consumer_id: str
    lease_seconds: int = 60


class MarkFinalDeliveredRequest(StrictContractModel):
    consumer_id: str | None = None


class MarkFinalFailedRequest(StrictContractModel):
    consumer_id: str | None = None
    error: str
    retry_after_seconds: int = 15
    non_retryable: bool = False
    error_class: str | None = None


class ToolResultEntry(StrictContractModel):
    tool_use_id: str
    content: Any = None
    is_error: bool | None = None


class AgentAssistantStreamEvent(ExtensibleContractModel):
    type: Literal["assistant"]
    message: AgentMessagePayload


class AgentUserStreamEvent(ExtensibleContractModel):
    type: Literal["user"]
    message: AgentMessagePayload | None = None
    content: list[ToolResultEntry] | None = None


class AgentToolStreamEvent(ExtensibleContractModel):
    type: Literal["tool"]
    content: list[ToolResultEntry]


class AgentReasoningStreamEvent(ExtensibleContractModel):
    type: Literal["reasoning"]
    text: str


class AgentCommandExecutionStreamEvent(ExtensibleContractModel):
    type: Literal["command_execution"]
    command: str | None = None
    aggregated_output: str | None = None
    exit_code: int | str | None = None
    status: str | None = None


class AgentFileChangeStreamEvent(ExtensibleContractModel):
    type: Literal["file_change"]
    changes: list[dict[str, Any]]


class AgentSubagentActivity(StrictContractModel):
    description: str
    toolName: str | None = None


class AgentSubagentStreamEvent(ExtensibleContractModel):
    type: Literal["subagent"]
    status: str
    subagent_id: str
    name: str | None = None
    summary: str | None = None
    error: str | None = None
    activity: str | None = None
    activities: list[AgentSubagentActivity] | None = None


class AgentResultStreamEvent(ExtensibleContractModel):
    type: Literal["result"]
    text: str | None = None
    result: str | None = None
    result_text: str | None = None
    error: str | None = None
    is_error: bool | None = None


class AgentErrorStreamEvent(ExtensibleContractModel):
    type: Literal["error"]
    error: str


class AgentSystemStreamEvent(ExtensibleContractModel):
    type: Literal["system", "session", "thread.started"]
    subtype: str | None = None
    session_id: str | None = None
    thread_id: str | None = None


class AgentUsageStreamEvent(ExtensibleContractModel):
    type: Literal["usage"]
    usage: dict[str, Any]
    model: str | None = None
    authoritative: bool | None = None


class AgentTurnDoneStreamEvent(ExtensibleContractModel):
    type: Literal["turn.done", "turn.completed"]
    turn_id: int | None = None
    result: str | None = None
    result_text: str | None = None
    text: str | None = None
    error: str | None = None
    is_error: bool | None = None
    repo_context: AgentRepoContext | None = None


class AgentExecutionStateEvent(ExtensibleContractModel):
    type: Literal["execution.state"]
    execution_id: str
    thread_key: str
    status: AgentExecutionStatus
    terminal_reason: AgentTerminalReason | None = None
    result_text: str | None = None
    error_text: str | None = None
    agent_thread_id: str | None = None
    repo_context: AgentRepoContext | None = None
    suppress_final_delivery: bool | None = None


class FinalDeliveryReadyEvent(FinalDeliveryPayload):
    type: Literal["final_delivery.ready"]
    execution_id: str
    thread_key: str
    status: AgentExecutionStatus


class FinalDeliveryDeliveredEvent(ExtensibleContractModel):
    type: Literal["final_delivery.delivered"]
    execution_id: str
    thread_key: str


CodexPassthroughEventType: TypeAlias = Literal[
    "turn.plan.updated",
    "item.started",
    "item.updated",
    "item.completed",
    "item.agentMessage.delta",
    "item.plan.delta",
    "item.commandExecution.outputDelta",
    "item.fileChange.outputDelta",
    "item.fileChange.patchUpdated",
    "item.reasoning.summaryTextDelta",
    "item.reasoning.summaryPartAdded",
    "item.reasoning.textDelta",
]


class CodexPassthroughStreamEvent(ExtensibleContractModel):
    type: CodexPassthroughEventType


class ObservationStreamEvent(ExtensibleContractModel):
    type: Annotated[str, Field(json_schema_extra={"x-ts-type": "`obs.${string}`"})]
    execution_id: str | None = None
    thread_key: str | None = None


class ExecutionSummaryStreamEvent(ExtensibleContractModel):
    type: Literal["execution.summary"]
    execution_id: str
    thread_key: str
    status: AgentExecutionStatus
    terminal_reason: AgentTerminalReason | None = None


class UnknownStreamData(ExtensibleContractModel):
    type: Literal["unknown"]
    raw: str


AgentStreamData: TypeAlias = (
    AgentAssistantStreamEvent
    | AgentUserStreamEvent
    | AgentToolStreamEvent
    | AgentReasoningStreamEvent
    | AgentCommandExecutionStreamEvent
    | AgentFileChangeStreamEvent
    | AgentSubagentStreamEvent
    | AgentResultStreamEvent
    | AgentErrorStreamEvent
    | AgentSystemStreamEvent
    | AgentUsageStreamEvent
    | AgentTurnDoneStreamEvent
    | AgentExecutionStateEvent
    | FinalDeliveryReadyEvent
    | FinalDeliveryDeliveredEvent
    | CodexPassthroughStreamEvent
    | ObservationStreamEvent
    | ExecutionSummaryStreamEvent
    | UnknownStreamData
)


AgentStreamEventKind: TypeAlias = Literal[
    "amp_raw_event",
    "execution_state",
    "execution_started",
    "execution_summary",
    "final_delivery_ready",
    "final_delivery_delivered",
    "assistant_message_observed",
    "assistant_text_observed",
    "assistant_tool_use_observed",
    "tool_result_observed",
    "reasoning_observed",
    "command_observed",
    "file_change_observed",
    "subagent_status_observed",
    "usage_observed",
    "result_observed",
    "error_observed",
    "message",
]


class StreamEvent(StrictContractModel):
    eventId: int
    eventKind: AgentStreamEventKind | str
    data: AgentStreamData


TS_EXPORTS: dict[str, Any] = {
    name: globals()[name]
    for name in [
        "AgentMessageRole",
        "AgentExecutionStatus",
        "AgentTerminalReason",
        "Base64Source",
        "TextContentBlock",
        "BinaryContentBlock",
        "AttachmentRefContentBlock",
        "ToolUseContentBlock",
        "ToolResultContentBlock",
        "AgentInputContentBlock",
        "AgentContentBlock",
        "AgentMessagePayload",
        "AgentInputMessagePayload",
        "AgentMessageEvent",
        "AgentDelivery",
        "SpawnRequest",
        "SpawnResult",
        "MessageRequest",
        "MessageAccepted",
        "BatchMessageItem",
        "BatchMessageRequest",
        "BatchMessageAccepted",
        "ExecuteRequest",
        "ExecutionAccepted",
        "SteerExecutionRequest",
        "AgentRepoContext",
        "AgentExecutionRecord",
        "ThreadExecutionSummary",
        "ThreadExecutionList",
        "ExecutionControlResult",
        "ReleaseRequest",
        "ReleaseThreadResult",
        "AgentStatus",
        "FinalDeliveryPayload",
        "FinalDeliveryRecord",
        "FinalDeliveryClaimResponse",
        "FinalDeliveryMutationResult",
        "ClaimFinalDeliveryRequest",
        "RenewFinalDeliveryLeaseRequest",
        "MarkFinalDeliveredRequest",
        "MarkFinalFailedRequest",
        "ToolResultEntry",
        "AgentStreamData",
        "AgentStreamEventKind",
        "StreamEvent",
    ]
}
