use std::convert::TryFrom;

use axum::response::sse::Event;
use centaur_session_core::{HarnessType, SessionEvent, SessionMessageInput, ThreadKey};
use centaur_session_runtime::SESSION_OUTPUT_LINE_EVENT;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CreateSessionRequest {
    pub harness_type: HarnessType,
    pub metadata: Option<Value>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AppendMessagesRequest {
    pub messages: Vec<SessionMessageInput>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AppendMessagesResponse {
    pub ok: bool,
    pub message_ids: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ExecuteSessionRequest {
    pub metadata: Option<Value>,
    #[serde(default)]
    pub input_lines: Vec<String>,
    pub idle_timeout_ms: Option<u64>,
    pub max_duration_ms: Option<u64>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ExecuteSessionResponse {
    pub ok: bool,
    pub execution_id: String,
    pub thread_key: ThreadKey,
    pub status: String,
}

#[derive(Clone, Copy, Debug, Deserialize)]
pub struct EventsQuery {
    pub after_event_id: Option<i64>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SessionEventName {
    OutputLine,
    ExecutionStarted,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionCancelled,
    StreamError,
    Other(String),
}

impl SessionEventName {
    pub fn as_str(&self) -> &str {
        match self {
            Self::OutputLine => SESSION_OUTPUT_LINE_EVENT,
            Self::ExecutionStarted => "session.execution_started",
            Self::ExecutionCompleted => "session.execution_completed",
            Self::ExecutionFailed => "session.execution_failed",
            Self::ExecutionCancelled => "session.execution_cancelled",
            Self::StreamError => "session.stream_error",
            Self::Other(value) => value.as_str(),
        }
    }
}

impl From<String> for SessionEventName {
    fn from(value: String) -> Self {
        match value.as_str() {
            SESSION_OUTPUT_LINE_EVENT => Self::OutputLine,
            "session.execution_started" => Self::ExecutionStarted,
            "session.execution_completed" => Self::ExecutionCompleted,
            "session.execution_failed" => Self::ExecutionFailed,
            "session.execution_cancelled" => Self::ExecutionCancelled,
            "session.stream_error" => Self::StreamError,
            _ => Self::Other(value),
        }
    }
}

impl From<&str> for SessionEventName {
    fn from(value: &str) -> Self {
        Self::from(value.to_owned())
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum SessionSseEvent {
    OutputLine {
        id: i64,
        line: String,
    },
    Json {
        id: i64,
        event_name: SessionEventName,
        payload: Value,
    },
}

impl SessionSseEvent {
    pub fn stream_error(message: impl Into<String>) -> Self {
        Self::Json {
            id: 0,
            event_name: SessionEventName::StreamError,
            payload: serde_json::json!({ "error": message.into() }),
        }
    }

    fn id(&self) -> i64 {
        match self {
            Self::OutputLine { id, .. } | Self::Json { id, .. } => *id,
        }
    }

    fn event_name(&self) -> &str {
        match self {
            Self::OutputLine { .. } => SESSION_OUTPUT_LINE_EVENT,
            Self::Json { event_name, .. } => event_name.as_str(),
        }
    }

    fn data(&self) -> String {
        match self {
            Self::OutputLine { line, .. } => line.clone(),
            Self::Json { payload, .. } => {
                serde_json::to_string(payload).unwrap_or_else(|_| "{}".to_owned())
            }
        }
    }
}

impl TryFrom<SessionEvent> for SessionSseEvent {
    type Error = SessionEventConversionError;

    fn try_from(event: SessionEvent) -> Result<Self, Self::Error> {
        let event_name = SessionEventName::from(event.event_type);
        match event_name {
            SessionEventName::OutputLine => {
                let Some(line) = event.payload.as_str() else {
                    return Err(SessionEventConversionError::OutputLinePayload {
                        event_id: event.event_id,
                    });
                };
                Ok(Self::OutputLine {
                    id: event.event_id,
                    line: line.to_owned(),
                })
            }
            event_name => Ok(Self::Json {
                id: event.event_id,
                event_name,
                payload: event.payload,
            }),
        }
    }
}

impl From<SessionSseEvent> for Event {
    fn from(value: SessionSseEvent) -> Self {
        Event::default()
            .id(value.id().to_string())
            .event(value.event_name())
            .data(value.data())
    }
}

#[derive(Clone, Debug, Error)]
pub enum SessionEventConversionError {
    #[error("session.output.line event {event_id} payload must be a string")]
    OutputLinePayload { event_id: i64 },
}
