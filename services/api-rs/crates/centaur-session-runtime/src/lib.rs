use std::{
    collections::{HashMap, VecDeque},
    sync::Arc,
    time::Duration,
};

use centaur_sandbox_core::{
    SandboxBackend, SandboxError, SandboxId, SandboxIoGuard, SandboxRead, SandboxSpec,
    SandboxStatus, SandboxWrite,
};
use centaur_session_core::{
    HarnessType, Session, SessionEvent, SessionExecution, SessionMessageInput, ThreadKey,
};
use centaur_session_sqlx::{PgSessionStore, SessionStoreError, default_metadata};
use futures_util::{SinkExt, Stream, StreamExt, stream};
use serde_json::{Value, json};
use thiserror::Error;
use tokio::{io, sync::Mutex, time::sleep};
use tokio_util::codec::{FramedRead, FramedWrite, LinesCodec, LinesCodecError};
use tracing::warn;

pub const SESSION_OUTPUT_LINE_EVENT: &str = "session.output.line";

const MAX_SESSION_OUTPUT_LINE_BYTES: usize = 1024 * 1024;
const DEFAULT_IDLE_TIMEOUT_MS: u64 = 1_000;
const DEFAULT_MAX_DURATION_MS: u64 = 60_000;

type SandboxSpecFactory = Arc<dyn Fn(&ThreadKey, &str) -> SandboxSpec + Send + Sync>;
type SessionInputSink = FramedWrite<SandboxWrite, LinesCodec>;

#[derive(Clone)]
pub struct SessionRuntime {
    store: PgSessionStore,
    sandbox_runtime: SandboxRuntime,
    sandbox_pipes: Arc<Mutex<HashMap<String, SessionPipe>>>,
}

#[derive(Clone)]
pub enum SandboxRuntime {
    Mock,
    Backend {
        backend: Arc<dyn SandboxBackend>,
        spec_factory: SandboxSpecFactory,
    },
}

#[derive(Debug)]
pub struct ExecuteSessionInput {
    pub metadata: Option<Value>,
    pub input_lines: Vec<String>,
    pub idle_timeout_ms: Option<u64>,
    pub max_duration_ms: Option<u64>,
}

#[derive(Clone)]
struct SessionPipe {
    stdin: Arc<Mutex<SessionInputSink>>,
}

struct EventStreamState {
    store: PgSessionStore,
    thread_key: ThreadKey,
    after_event_id: i64,
    pending: VecDeque<SessionEvent>,
    done: bool,
}

impl SessionRuntime {
    pub fn new(store: PgSessionStore, sandbox_runtime: SandboxRuntime) -> Self {
        Self {
            store,
            sandbox_runtime,
            sandbox_pipes: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub async fn create_or_get_session(
        &self,
        thread_key: &ThreadKey,
        harness_type: &HarnessType,
        metadata: Option<Value>,
    ) -> Result<Session, SessionRuntimeError> {
        Ok(self
            .store
            .create_or_get_session(thread_key, harness_type, default_metadata(metadata))
            .await?)
    }

    pub async fn append_messages(
        &self,
        thread_key: &ThreadKey,
        messages: &[SessionMessageInput],
    ) -> Result<Vec<String>, SessionRuntimeError> {
        if messages.is_empty() {
            return Err(SessionRuntimeError::BadRequest(
                "messages must not be empty".to_owned(),
            ));
        }
        Ok(self.store.append_messages(thread_key, messages).await?)
    }

    pub async fn execute_session(
        &self,
        thread_key: &ThreadKey,
        input: ExecuteSessionInput,
    ) -> Result<SessionExecution, SessionRuntimeError> {
        let session = self.store.get_session(thread_key).await?;
        validate_input_lines(&input.input_lines)?;
        let pipe_options = PipeOptions::from_input(&input)?;

        let execution = self
            .store
            .create_execution(thread_key, default_metadata(input.metadata))
            .await?;
        let execution = self
            .store
            .mark_execution_running(&execution.execution_id)
            .await?;
        let sandbox_id = self
            .ensure_session_sandbox(
                thread_key,
                session.sandbox_id.as_deref(),
                &execution.execution_id,
            )
            .await?;

        self.store
            .append_event(
                thread_key,
                Some(&execution.execution_id),
                "session.execution_started",
                json!({
                    "execution_id": execution.execution_id,
                    "thread_key": thread_key.as_str(),
                    "input_line_count": input.input_lines.len(),
                }),
            )
            .await?;

        let run_result = match &self.sandbox_runtime {
            SandboxRuntime::Mock => {
                run_mock_session_pipe(
                    &self.store,
                    thread_key,
                    &execution.execution_id,
                    &sandbox_id,
                    pipe_options,
                )
                .await
            }
            SandboxRuntime::Backend { backend, .. } => {
                let pipe = self
                    .ensure_session_pipe(backend.clone(), thread_key, &sandbox_id)
                    .await;
                match pipe {
                    Ok(pipe) => write_input_lines(&pipe, &input.input_lines)
                        .await
                        .map(|()| 0),
                    Err(error) => Err(error),
                }
            }
        };

        let output_line_count = match run_result {
            Ok(output_line_count) => output_line_count,
            Err(error) => {
                let error_message = error.to_string();
                let _ = self
                    .store
                    .append_event(
                        thread_key,
                        Some(&execution.execution_id),
                        "session.execution_failed",
                        json!({
                            "execution_id": execution.execution_id,
                            "thread_key": thread_key.as_str(),
                            "error": error_message,
                        }),
                    )
                    .await;
                let _ = self
                    .store
                    .fail_execution(&execution.execution_id, &error_message)
                    .await;
                return Err(error);
            }
        };

        self.store
            .append_event(
                thread_key,
                Some(&execution.execution_id),
                "session.execution_completed",
                json!({
                    "execution_id": execution.execution_id,
                    "thread_key": thread_key.as_str(),
                    "output_line_count": output_line_count,
                    "completion_reason": "input_accepted",
                }),
            )
            .await?;

        Ok(self
            .store
            .complete_execution(&execution.execution_id)
            .await?)
    }

    pub async fn stream_events(
        &self,
        thread_key: &ThreadKey,
        after_event_id: i64,
    ) -> Result<
        impl Stream<Item = Result<SessionEvent, SessionRuntimeError>> + use<>,
        SessionRuntimeError,
    > {
        let session = self.store.get_session(thread_key).await?;
        if let Some(sandbox_id) = session.sandbox_id.as_deref()
            && let SandboxRuntime::Backend { backend, .. } = &self.sandbox_runtime
        {
            self.ensure_session_pipe(backend.clone(), thread_key, sandbox_id)
                .await?;
        }

        Ok(session_event_stream(
            self.store.clone(),
            thread_key.clone(),
            after_event_id,
        ))
    }

    async fn ensure_session_sandbox(
        &self,
        thread_key: &ThreadKey,
        existing_sandbox_id: Option<&str>,
        execution_id: &str,
    ) -> Result<String, SessionRuntimeError> {
        match &self.sandbox_runtime {
            SandboxRuntime::Mock => {
                if let Some(sandbox_id) = existing_sandbox_id {
                    return Ok(sandbox_id.to_owned());
                }
                let sandbox_id = format!("mock-sandbox-{execution_id}");
                self.store
                    .update_sandbox_id(thread_key, Some(&sandbox_id))
                    .await?;
                Ok(sandbox_id)
            }
            SandboxRuntime::Backend {
                backend,
                spec_factory,
            } => {
                if let Some(sandbox_id) = existing_sandbox_id {
                    let id = SandboxId::new(sandbox_id);
                    match backend.status(&id).await {
                        Ok(SandboxStatus::Running | SandboxStatus::Created) => {
                            return Ok(sandbox_id.to_owned());
                        }
                        Ok(_) | Err(SandboxError::NotFound(_)) => {}
                        Err(error) => return Err(SessionRuntimeError::Sandbox(error)),
                    }
                }

                let spec = spec_factory(thread_key, execution_id);
                let handle = backend.create(spec).await?;
                self.store
                    .update_sandbox_id(thread_key, Some(handle.id.as_str()))
                    .await?;
                Ok(handle.id.into_string())
            }
        }
    }

    async fn ensure_session_pipe(
        &self,
        backend: Arc<dyn SandboxBackend>,
        thread_key: &ThreadKey,
        sandbox_id: &str,
    ) -> Result<SessionPipe, SessionRuntimeError> {
        if let Some(pipe) = self.sandbox_pipes.lock().await.get(sandbox_id).cloned() {
            return Ok(pipe);
        }

        let io = backend
            .open_io(&SandboxId::new(sandbox_id))
            .await?
            .into_parts();
        let pipe = SessionPipe {
            stdin: Arc::new(Mutex::new(FramedWrite::new(
                io.stdin,
                LinesCodec::new_with_max_length(MAX_SESSION_OUTPUT_LINE_BYTES),
            ))),
        };

        self.sandbox_pipes
            .lock()
            .await
            .insert(sandbox_id.to_owned(), pipe.clone());
        let store = self.store.clone();
        let thread_key = thread_key.clone();
        let pump_key = sandbox_id.to_owned();
        let sandbox_pipes = self.sandbox_pipes.clone();
        let stdout = io.stdout;
        let stderr = io.stderr;
        let guard = io.guard;
        let stderr_key = pump_key.clone();

        tokio::spawn(async move {
            let result =
                run_stdout_pump(store.clone(), thread_key.clone(), &pump_key, stdout, guard).await;
            if let Err(error) = result {
                warn!(%pump_key, %error, "session stdout pump failed");
                let _ = store
                    .append_event(
                        &thread_key,
                        None,
                        "session.stdout_pump_failed",
                        json!({
                            "sandbox_id": pump_key.as_str(),
                            "error": error.to_string(),
                        }),
                    )
                    .await;
            }
            sandbox_pipes.lock().await.remove(&pump_key);
        });

        tokio::spawn(async move {
            if let Err(error) = drain_stderr(stderr).await {
                warn!(%stderr_key, %error, "session stderr drain failed");
            }
        });

        Ok(pipe)
    }
}

impl SandboxRuntime {
    pub fn backend(backend: Arc<dyn SandboxBackend>, spec: SandboxSpec) -> Self {
        let spec_factory = move |_thread_key: &ThreadKey, _execution_id: &str| spec.clone();
        Self::backend_with_spec_factory(backend, spec_factory)
    }

    pub fn backend_with_spec_factory<F>(backend: Arc<dyn SandboxBackend>, spec_factory: F) -> Self
    where
        F: Fn(&ThreadKey, &str) -> SandboxSpec + Send + Sync + 'static,
    {
        Self::Backend {
            backend,
            spec_factory: Arc::new(spec_factory),
        }
    }
}

fn session_event_stream(
    store: PgSessionStore,
    thread_key: ThreadKey,
    after_event_id: i64,
) -> impl Stream<Item = Result<SessionEvent, SessionRuntimeError>> {
    stream::unfold(
        EventStreamState {
            store,
            thread_key,
            after_event_id,
            pending: VecDeque::new(),
            done: false,
        },
        |mut state| async move {
            loop {
                if let Some(event) = state.pending.pop_front() {
                    state.after_event_id = event.event_id;
                    return Some((Ok(event), state));
                }
                if state.done {
                    return None;
                }
                match state
                    .store
                    .list_events_after(&state.thread_key, state.after_event_id, 100)
                    .await
                {
                    Ok(events) if events.is_empty() => sleep(Duration::from_millis(250)).await,
                    Ok(events) => state.pending = events.into(),
                    Err(error) => {
                        state.done = true;
                        return Some((Err(SessionRuntimeError::Store(error)), state));
                    }
                }
            }
        },
    )
}

async fn run_mock_session_pipe(
    store: &PgSessionStore,
    thread_key: &ThreadKey,
    execution_id: &str,
    sandbox_id: &str,
    options: PipeOptions,
) -> Result<usize, SessionRuntimeError> {
    let mut output_line_count = 0;
    let output_lines = mock_app_server_output_lines(thread_key, execution_id, sandbox_id);
    for (index, line) in output_lines.iter().enumerate() {
        append_output_line(store, thread_key, Some(execution_id), line).await?;
        output_line_count += 1;
        if index + 1 < output_lines.len() {
            sleep(Duration::from_millis(200)).await;
        }
    }
    if options.idle_timeout < Duration::from_millis(DEFAULT_IDLE_TIMEOUT_MS)
        || options.max_duration < Duration::from_millis(DEFAULT_MAX_DURATION_MS)
    {
        sleep(options.idle_timeout).await;
    }
    Ok(output_line_count)
}

async fn run_stdout_pump(
    store: PgSessionStore,
    thread_key: ThreadKey,
    sandbox_id: &str,
    stdout: SandboxRead,
    _guard: SandboxIoGuard,
) -> Result<(), SessionRuntimeError> {
    let mut stdout = FramedRead::new(
        stdout,
        LinesCodec::new_with_max_length(MAX_SESSION_OUTPUT_LINE_BYTES),
    );
    while let Some(line) = stdout.next().await {
        let line = line.map_err(codec_error_to_runtime)?;
        append_output_line(&store, &thread_key, None, &line).await?;
    }
    store
        .append_event(
            &thread_key,
            None,
            "session.stdout_eof",
            json!({
                "sandbox_id": sandbox_id,
            }),
        )
        .await?;
    Ok(())
}

async fn drain_stderr(mut stderr: SandboxRead) -> Result<(), SessionRuntimeError> {
    io::copy(&mut stderr, &mut io::sink())
        .await
        .map_err(|err| {
            SessionRuntimeError::Sandbox(SandboxError::Io(format!("drain stderr: {err}")))
        })?;
    Ok(())
}

async fn write_input_lines(
    pipe: &SessionPipe,
    input_lines: &[String],
) -> Result<(), SessionRuntimeError> {
    let mut stdin = pipe.stdin.lock().await;
    for line in input_lines {
        stdin.send(line).await.map_err(codec_error_to_runtime)?;
    }
    Ok(())
}

async fn append_output_line(
    store: &PgSessionStore,
    thread_key: &ThreadKey,
    execution_id: Option<&str>,
    line: &str,
) -> Result<(), SessionRuntimeError> {
    store
        .append_event(
            thread_key,
            execution_id,
            SESSION_OUTPUT_LINE_EVENT,
            Value::String(line.to_owned()),
        )
        .await?;
    Ok(())
}

fn mock_app_server_output_lines(
    thread_key: &ThreadKey,
    execution_id: &str,
    sandbox_id: &str,
) -> Vec<String> {
    let mock_thread_id = format!("mock-codex-thread-{sandbox_id}");
    let mut lines = vec![
        json!({
            "type": "system",
            "subtype": "wrapper_heartbeat",
            "phase": "startup",
            "thread_key": thread_key.as_str(),
            "execution_id": execution_id,
            "sandbox_id": sandbox_id,
        }),
        json!({
            "type": "system",
            "subtype": "wrapper_heartbeat",
            "phase": "app_server_started",
            "thread_key": thread_key.as_str(),
            "execution_id": execution_id,
            "sandbox_id": sandbox_id,
        }),
        json!({
            "type": "thread.started",
            "thread_id": mock_thread_id,
        }),
    ];

    for turn_index in 1..=3 {
        let mock_turn_id = format!("mock-turn-{execution_id}-{turn_index}");
        lines.extend([
            json!({
                "type": "turn.started",
                "turn_id": mock_turn_id,
            }),
            json!({
                "type": "item.agentMessage.delta",
                "turnId": mock_turn_id,
                "session_id": mock_thread_id,
                "delta": format!("PONG {turn_index}"),
            }),
            json!({
                "type": "turn.completed",
                "turn": {
                    "id": mock_turn_id,
                },
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 1,
                },
            }),
        ]);
    }

    lines.into_iter().map(|value| value.to_string()).collect()
}

fn validate_input_lines(lines: &[String]) -> Result<(), SessionRuntimeError> {
    for (index, line) in lines.iter().enumerate() {
        if line.contains('\n') || line.contains('\r') {
            return Err(SessionRuntimeError::BadRequest(format!(
                "input_lines[{index}] must be one line"
            )));
        }
    }
    Ok(())
}

fn codec_error_to_runtime(error: LinesCodecError) -> SessionRuntimeError {
    SessionRuntimeError::Sandbox(SandboxError::Io(error.to_string()))
}

#[derive(Clone, Copy, Debug)]
struct PipeOptions {
    idle_timeout: Duration,
    max_duration: Duration,
}

impl PipeOptions {
    fn from_input(input: &ExecuteSessionInput) -> Result<Self, SessionRuntimeError> {
        let idle_timeout = input
            .idle_timeout_ms
            .map(nonzero_duration_millis)
            .transpose()?
            .unwrap_or_else(|| Duration::from_millis(DEFAULT_IDLE_TIMEOUT_MS));
        let max_duration = input
            .max_duration_ms
            .map(nonzero_duration_millis)
            .transpose()?
            .unwrap_or_else(|| Duration::from_millis(DEFAULT_MAX_DURATION_MS));

        if idle_timeout > max_duration {
            return Err(SessionRuntimeError::BadRequest(
                "idle_timeout_ms must be less than or equal to max_duration_ms".to_owned(),
            ));
        }

        Ok(Self {
            idle_timeout,
            max_duration,
        })
    }
}

fn nonzero_duration_millis(value: u64) -> Result<Duration, SessionRuntimeError> {
    if value == 0 {
        return Err(SessionRuntimeError::BadRequest(
            "duration values must be greater than zero".to_owned(),
        ));
    }
    Ok(Duration::from_millis(value))
}

#[derive(Debug, Error)]
pub enum SessionRuntimeError {
    #[error("{0}")]
    BadRequest(String),
    #[error(transparent)]
    Store(#[from] SessionStoreError),
    #[error(transparent)]
    Sandbox(#[from] SandboxError),
}
