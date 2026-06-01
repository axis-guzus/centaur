use std::convert::Infallible;

use axum::{
    Json, Router,
    extract::{Path, Query, State},
    http::StatusCode,
    response::{
        IntoResponse, Response, Sse,
        sse::{Event, KeepAlive},
    },
    routing::{get, post},
};
use centaur_session_core::{HarnessType, SessionEvent, SessionMessageInput, ThreadKey};
use centaur_session_runtime::{
    ExecuteSessionInput, SESSION_OUTPUT_LINE_EVENT, SessionRuntimeError,
};
pub use centaur_session_runtime::{SandboxRuntime, SessionRuntime};
use centaur_session_sqlx::{PgSessionStore, SessionStoreError};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use thiserror::Error;

#[derive(Clone)]
pub struct AppState {
    runtime: SessionRuntime,
}

pub fn build_router_with_runtime(store: PgSessionStore, sandbox_runtime: SandboxRuntime) -> Router {
    build_router_with_session_runtime(SessionRuntime::new(store, sandbox_runtime))
}

pub fn build_router_with_session_runtime(runtime: SessionRuntime) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/api/session/{thread_key}", post(create_or_get_session))
        .route("/api/session/{thread_key}/messages", post(append_messages))
        .route("/api/session/{thread_key}/execute", post(execute_session))
        .route("/api/session/{thread_key}/events", get(stream_events))
        .with_state(AppState { runtime })
}

async fn healthz() -> Json<Value> {
    Json(json!({"ok": true}))
}

async fn create_or_get_session(
    State(state): State<AppState>,
    Path(raw_thread_key): Path<String>,
    Json(request): Json<CreateSessionRequest>,
) -> Result<Json<Value>, ApiError> {
    let thread_key = parse_thread_key(raw_thread_key)?;
    let session = state
        .runtime
        .create_or_get_session(&thread_key, &request.harness_type, request.metadata)
        .await?;
    Ok(Json(serde_json::to_value(session)?))
}

async fn append_messages(
    State(state): State<AppState>,
    Path(raw_thread_key): Path<String>,
    Json(request): Json<AppendMessagesRequest>,
) -> Result<Json<AppendMessagesResponse>, ApiError> {
    let thread_key = parse_thread_key(raw_thread_key)?;
    let message_ids = state
        .runtime
        .append_messages(&thread_key, &request.messages)
        .await?;
    Ok(Json(AppendMessagesResponse {
        ok: true,
        message_ids,
    }))
}

async fn execute_session(
    State(state): State<AppState>,
    Path(raw_thread_key): Path<String>,
    Json(request): Json<ExecuteSessionRequest>,
) -> Result<Json<ExecuteSessionResponse>, ApiError> {
    let thread_key = parse_thread_key(raw_thread_key)?;
    let execution = state
        .runtime
        .execute_session(
            &thread_key,
            ExecuteSessionInput {
                metadata: request.metadata,
                input_lines: request.input_lines,
                idle_timeout_ms: request.idle_timeout_ms,
                max_duration_ms: request.max_duration_ms,
            },
        )
        .await?;
    Ok(Json(ExecuteSessionResponse {
        ok: true,
        execution_id: execution.execution_id,
        thread_key: execution.thread_key,
        status: execution.status.to_string(),
    }))
}

async fn stream_events(
    State(state): State<AppState>,
    Path(raw_thread_key): Path<String>,
    Query(query): Query<EventsQuery>,
) -> Result<Sse<impl futures_util::Stream<Item = Result<Event, Infallible>>>, ApiError> {
    let thread_key = parse_thread_key(raw_thread_key)?;
    let events = state
        .runtime
        .stream_events(&thread_key, query.after_event_id.unwrap_or(0))
        .await?;
    let stream = events.map(|result| {
        Ok(match result {
            Ok(event) => to_sse_event(event),
            Err(error) => Event::default()
                .event("session.stream_error")
                .data(json!({"error": error.to_string()}).to_string()),
        })
    });
    Ok(Sse::new(stream).keep_alive(KeepAlive::default()))
}

fn to_sse_event(event: SessionEvent) -> Event {
    let data = if event.event_type == SESSION_OUTPUT_LINE_EVENT {
        event.payload.as_str().unwrap_or_default().to_owned()
    } else {
        serde_json::to_string(&event.payload).unwrap_or_else(|_| "{}".to_owned())
    };
    Event::default()
        .id(event.event_id.to_string())
        .event(event.event_type)
        .data(data)
}

fn parse_thread_key(value: String) -> Result<ThreadKey, ApiError> {
    ThreadKey::parse(value).map_err(|error| ApiError::BadRequest(error.to_string()))
}

#[derive(Debug, Deserialize)]
struct CreateSessionRequest {
    harness_type: HarnessType,
    metadata: Option<Value>,
}

#[derive(Debug, Deserialize)]
struct AppendMessagesRequest {
    messages: Vec<SessionMessageInput>,
}

#[derive(Debug, Serialize)]
struct AppendMessagesResponse {
    ok: bool,
    message_ids: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct ExecuteSessionRequest {
    metadata: Option<Value>,
    #[serde(default)]
    input_lines: Vec<String>,
    idle_timeout_ms: Option<u64>,
    max_duration_ms: Option<u64>,
}

#[derive(Debug, Serialize)]
struct ExecuteSessionResponse {
    ok: bool,
    execution_id: String,
    thread_key: ThreadKey,
    status: String,
}

#[derive(Debug, Deserialize)]
struct EventsQuery {
    after_event_id: Option<i64>,
}

#[derive(Debug, Error)]
enum ApiError {
    #[error("{0}")]
    BadRequest(String),
    #[error(transparent)]
    Runtime(#[from] SessionRuntimeError),
    #[error(transparent)]
    Serialize(#[from] serde_json::Error),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let status = match &self {
            Self::BadRequest(_) => StatusCode::BAD_REQUEST,
            Self::Runtime(SessionRuntimeError::BadRequest(_)) => StatusCode::BAD_REQUEST,
            Self::Runtime(SessionRuntimeError::Store(SessionStoreError::NotFound { .. })) => {
                StatusCode::NOT_FOUND
            }
            Self::Runtime(SessionRuntimeError::Store(SessionStoreError::HarnessConflict {
                ..
            })) => StatusCode::CONFLICT,
            Self::Runtime(_) | Self::Serialize(_) => StatusCode::INTERNAL_SERVER_ERROR,
        };
        let body = Json(json!({
            "ok": false,
            "error": self.to_string(),
        }));
        (status, body).into_response()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    };

    use async_trait::async_trait;
    use centaur_sandbox_core::{
        ObservedSandbox, SandboxBackend, SandboxError, SandboxHandle, SandboxId, SandboxIo,
        SandboxResult, SandboxSpec, SandboxStatus,
    };
    use centaur_session_runtime::SandboxRuntime;
    use centaur_session_sqlx::PgSessionStore;
    use sqlx::PgPool;

    use super::build_router_with_runtime;

    #[tokio::test]
    async fn router_builds() {
        let pool =
            PgPool::connect_lazy("postgres://postgres:postgres@localhost/centaur_test").unwrap();
        let _router = build_router_with_runtime(
            PgSessionStore::new(pool),
            SandboxRuntime::backend(Arc::new(TestBackend::default()), SandboxSpec::new("test")),
        );
    }

    #[derive(Default)]
    struct TestBackend {
        next_id: AtomicU64,
    }

    #[async_trait]
    impl SandboxBackend for TestBackend {
        fn name(&self) -> &'static str {
            "test"
        }

        async fn create(&self, _spec: SandboxSpec) -> SandboxResult<SandboxHandle> {
            let id = self.next_id.fetch_add(1, Ordering::Relaxed) + 1;
            Ok(SandboxHandle::new(
                SandboxId::new(format!("test-{id}")),
                self.name(),
            ))
        }

        async fn open_io(&self, _id: &SandboxId) -> SandboxResult<SandboxIo> {
            unreachable!("router construction should not open sandbox I/O")
        }

        async fn status(&self, _id: &SandboxId) -> SandboxResult<SandboxStatus> {
            Ok(SandboxStatus::Running)
        }

        async fn observe(&self, id: &SandboxId) -> SandboxResult<ObservedSandbox> {
            Ok(ObservedSandbox::new(
                id.clone(),
                self.name(),
                SandboxStatus::Running,
            ))
        }

        async fn list_observed(&self) -> SandboxResult<Vec<ObservedSandbox>> {
            Ok(Vec::new())
        }

        async fn stop(&self, _id: &SandboxId) -> SandboxResult<()> {
            Ok(())
        }

        async fn pause(&self, _id: &SandboxId) -> SandboxResult<()> {
            Err(SandboxError::Unsupported {
                backend: self.name(),
                operation: "pause",
            })
        }

        async fn resume(&self, _id: &SandboxId) -> SandboxResult<()> {
            Err(SandboxError::Unsupported {
                backend: self.name(),
                operation: "resume",
            })
        }
    }
}
