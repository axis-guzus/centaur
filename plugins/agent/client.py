"""Agent sandbox — 1 Slack thread = 1 Docker container.

Manages container lifecycle and executes harness CLI commands (amp,
claude-code, codex) inside them. Returns the final result text.
"""

import codecs
import json
import os
import time
from typing import Any

import docker
from docker.errors import NotFound

HARNESSES = ("amp", "claude-code", "codex")

# In-memory session registry: slack_thread_key → session dict
_sessions: dict[str, dict[str, Any]] = {}


def _docker_client() -> docker.DockerClient:
    return docker.from_env()


def _image() -> str:
    return os.getenv("AGENT_IMAGE", "tempo-agent:latest")


def _container_env() -> list[str]:
    """Build env vars to forward into the container."""
    keys = [
        "AMP_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "API_SECRET_KEY",
    ]
    env = [
        f"AI_V2_API_URL={os.getenv('AI_V2_API_URL', 'http://localhost:8000')}",
        f"AI_V2_API_KEY={os.getenv('API_SECRET_KEY', '')}",
    ]
    for k in keys:
        v = os.getenv(k, "")
        if v:
            env.append(f"{k}={v}")
    return env


def _build_command(
    harness: str, message: str, thread_id: str | None
) -> list[str]:
    if harness == "claude-code":
        return [
            "claude",
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            *(["--continue", thread_id] if thread_id else []),
            "-p", message,
        ]
    if harness == "codex":
        return [
            "codex", "exec", "--json",
            *(["resume", thread_id] if thread_id else []),
            message,
        ]
    # Default: amp
    return [
        "amp",
        "--no-ide",
        "--no-notifications",
        "--dangerously-allow-all",
        "--stream-json",
        *(["threads", "continue", thread_id] if thread_id else []),
        "-x", message,
    ]


def _extract_result(raw_lines: list[str], harness: str) -> tuple[str, str | None]:
    """Parse JSON-line output from a harness CLI.

    Returns (result_text, agent_thread_id).
    """
    result_text = ""
    agent_thread_id: str | None = None

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Codex normalization
        if harness == "codex":
            etype = event.get("type", "")
            if etype == "thread.started":
                agent_thread_id = event.get("thread_id")
            elif etype == "turn.completed":
                items = event.get("items", [])
                msgs = [i for i in items if i.get("type") == "agent_message"]
                if msgs:
                    result_text = msgs[-1].get("text", "")
            elif etype == "error":
                result_text = f"❌ {event.get('message', 'Unknown error')}"
            continue

        # Amp / claude-code format
        etype = event.get("type", "")
        if etype == "system" and event.get("subtype") == "init":
            agent_thread_id = event.get("session_id")
        elif etype == "result":
            result_text = event.get("result", "")
        elif etype == "assistant" and event.get("message", {}).get("content"):
            for part in event["message"]["content"]:
                if part.get("type") == "text" and part.get("text"):
                    result_text = part["text"]
        elif etype == "error":
            result_text = f"❌ {event.get('error', 'Unknown error')}"

    return result_text, agent_thread_id


class AgentClient:
    """Manage Docker sandbox containers for agent harness execution."""

    def spawn(
        self,
        slack_thread_key: str,
        harness: str = "amp",
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Spawn a new sandbox container for a Slack thread.

        Args:
            slack_thread_key: Unique thread ID (e.g. "C04ABC:1234567890.123456")
            harness: Agent CLI to use — amp, claude-code, or codex
            repo: Optional repo path to set as working directory
        """
        if harness not in HARNESSES:
            raise RuntimeError(f"Unknown harness: {harness}. Use one of {HARNESSES}")

        # Reuse existing container if alive
        existing = _sessions.get(slack_thread_key)
        if existing:
            try:
                client = _docker_client()
                container = client.containers.get(existing["container_id"])
                if container.status == "running":
                    return {
                        "session_id": slack_thread_key,
                        "container_id": existing["container_id"],
                        "status": "already_running",
                        "harness": existing["harness"],
                    }
                container.start()
                existing["state"] = "running"
                return {
                    "session_id": slack_thread_key,
                    "container_id": existing["container_id"],
                    "status": "restarted",
                    "harness": existing["harness"],
                }
            except NotFound:
                del _sessions[slack_thread_key]

        client = _docker_client()
        workdir = f"/repos/{repo}" if repo else "/repos"

        container = client.containers.run(
            _image(),
            detach=True,
            stdin_open=True,
            tty=False,
            network_mode="host",
            mem_limit="4g",
            nano_cpus=int(2 * 1e9),
            environment=_container_env(),
            working_dir=workdir,
            labels={
                "tempo.agent": "true",
                "tempo.thread": slack_thread_key,
                "tempo.harness": harness,
            },
            name=f"tempo-agent-{slack_thread_key.replace(':', '-')[:40]}",
        )

        session = {
            "container_id": container.id,
            "harness": harness,
            "agent_thread_id": None,
            "state": "running",
            "created_at": time.time(),
            "last_activity": time.time(),
        }
        _sessions[slack_thread_key] = session

        return {
            "session_id": slack_thread_key,
            "container_id": container.id,
            "status": "started",
            "harness": harness,
        }

    def execute(
        self,
        slack_thread_key: str,
        message: str,
    ) -> dict[str, Any]:
        """Execute a message in an existing sandbox and return the result.

        Runs the harness CLI via docker exec, waits for completion,
        and returns the final result text.
        """
        session = _sessions.get(slack_thread_key)
        if not session:
            raise RuntimeError(
                f"No session for thread '{slack_thread_key}'. Call spawn() first."
            )

        client = _docker_client()
        try:
            container = client.containers.get(session["container_id"])
        except NotFound:
            del _sessions[slack_thread_key]
            raise RuntimeError("Container is gone. Call spawn() to create a new one.")

        cmd = _build_command(
            session["harness"], message, session["agent_thread_id"]
        )

        session["state"] = "working"
        session["last_activity"] = time.time()

        # Use low-level exec API for streaming
        api = client.api
        exec_id = api.exec_create(
            container.id,
            cmd,
            stdout=True,
            stderr=True,
            environment={
                "THREAD_ID": session["agent_thread_id"] or "",
            },
        )["Id"]

        output = api.exec_start(exec_id, stream=True, demux=True)

        # Collect output lines
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        lines: list[str] = []
        buf = ""

        for stdout_chunk, stderr_chunk in output:
            if stdout_chunk:
                buf += decoder.decode(stdout_chunk)
                while "\n" in buf:
                    idx = buf.index("\n")
                    lines.append(buf[:idx])
                    buf = buf[idx + 1:]

        # Flush remaining buffer
        if buf.strip():
            lines.append(buf)

        result_text, agent_thread_id = _extract_result(lines, session["harness"])

        if agent_thread_id:
            session["agent_thread_id"] = agent_thread_id

        session["state"] = "idle"
        session["last_activity"] = time.time()

        return {
            "session_id": slack_thread_key,
            "result": result_text,
            "agent_thread_id": session["agent_thread_id"],
            "harness": session["harness"],
        }

    def status(self, slack_thread_key: str | None = None) -> dict[str, Any]:
        """Get session status. If no key given, list all sessions."""
        if slack_thread_key:
            session = _sessions.get(slack_thread_key)
            if not session:
                return {"error": f"No session for '{slack_thread_key}'"}
            return {
                "session_id": slack_thread_key,
                **session,
            }

        return {
            "sessions": [
                {"session_id": k, **v} for k, v in _sessions.items()
            ],
            "count": len(_sessions),
        }

    def stop(self, slack_thread_key: str) -> dict[str, Any]:
        """Stop and remove a sandbox container."""
        session = _sessions.get(slack_thread_key)
        if not session:
            return {"error": f"No session for '{slack_thread_key}'"}

        client = _docker_client()
        try:
            container = client.containers.get(session["container_id"])
            container.stop(timeout=5)
            container.remove()
        except Exception:
            pass

        del _sessions[slack_thread_key]
        return {"session_id": slack_thread_key, "status": "stopped"}

    def interrupt(self, slack_thread_key: str) -> dict[str, Any]:
        """Interrupt the currently running command in a sandbox."""
        session = _sessions.get(slack_thread_key)
        if not session:
            return {"error": f"No session for '{slack_thread_key}'"}

        client = _docker_client()
        try:
            container = client.containers.get(session["container_id"])
            harness = session["harness"]
            target = {
                "amp": "amp",
                "claude-code": "claude",
                "codex": "codex",
            }.get(harness, "amp")
            container.exec_run(["pkill", "-INT", "-f", target], detach=True)
        except Exception:
            pass

        return {"session_id": slack_thread_key, "status": "interrupted"}


def _client() -> AgentClient:
    return AgentClient()
