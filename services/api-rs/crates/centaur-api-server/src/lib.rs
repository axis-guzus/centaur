use std::{convert::Infallible, sync::Arc};

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
use centaur_sandbox_core::SandboxSpec;
use centaur_sandbox_local::LocalSandboxBackend;
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

pub fn build_router(store: PgSessionStore) -> Router {
    build_router_with_runtime(store, local_mock_sandbox_runtime())
}

pub fn build_router_with_runtime(store: PgSessionStore, sandbox_runtime: SandboxRuntime) -> Router {
    build_router_with_session_runtime(SessionRuntime::new(store, sandbox_runtime))
}

pub fn local_mock_sandbox_runtime() -> SandboxRuntime {
    SandboxRuntime::backend(
        Arc::new(LocalSandboxBackend::new()),
        local_mock_app_server_spec(),
    )
}

pub fn local_mock_app_server_spec() -> SandboxSpec {
    SandboxSpec::new("/bin/sh")
        .command(["/bin/sh", "-lc"])
        .args([mock_app_server_script()])
}

pub fn mock_app_server_script() -> &'static str {
    r#"while IFS= read -r line; do
printf '%s\n' '{"type":"system","subtype":"wrapper_heartbeat","phase":"startup"}'
sleep 0.2
printf '%s\n' '{"type":"system","subtype":"wrapper_heartbeat","phase":"app_server_started"}'
sleep 0.2
printf '%s\n' '{"type":"thread.started","thread_id":"mock-codex-thread"}'
sleep 0.2
turn_index=1
while [ "$turn_index" -le 3 ]; do
  turn_id="mock-turn-$turn_index"
  printf '{"type":"turn.started","turn_id":"%s"}\n' "$turn_id"
  sleep 0.2
  printf '{"type":"item.agentMessage.delta","turnId":"%s","session_id":"mock-codex-thread","delta":"PONG %s"}\n' "$turn_id" "$turn_index"
  sleep 0.2
  printf '{"type":"turn.completed","turn":{"id":"%s"},"usage":{"input_tokens":0,"output_tokens":1}}\n' "$turn_id"
  sleep 0.2
  turn_index=$((turn_index + 1))
done
done"#
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
    use super::build_router;
    use centaur_session_sqlx::PgSessionStore;
    use sqlx::PgPool;

    #[tokio::test]
    async fn router_builds() {
        let pool =
            PgPool::connect_lazy("postgres://postgres:postgres@localhost/centaur_test").unwrap();
        let _router = build_router(PgSessionStore::new(pool));
    }
}
