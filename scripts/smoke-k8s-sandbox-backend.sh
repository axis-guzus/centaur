#!/usr/bin/env bash
set -euo pipefail

CONTEXT="${1:-${KUBECTL_CONTEXT:-}}"
NAMESPACE="${2:-${CENTAUR_NAMESPACE:-centaur}}"
RELEASE="${3:-${CENTAUR_RELEASE:-centaur}}"
DEPLOYMENT="${4:-${RELEASE}-centaur-api}"
THREAD_KEY="smoke-k8s-$(date +%s)"

KUBECTL=(kubectl)
if [ -n "$CONTEXT" ]; then
  KUBECTL+=(--context "$CONTEXT")
fi

"${KUBECTL[@]}" -n "$NAMESPACE" exec "deploy/${DEPLOYMENT}" -- env SMOKE_THREAD_KEY="$THREAD_KEY" sh -lc '
cat >/tmp/smoke_k8s_backend.py <<"PY"
import asyncio
import contextlib
import json
import os

from api.agent import _drop_runtime, _get_runtime
from api.sandbox.registry import get_backend


async def main() -> None:
    backend = get_backend()
    session = await backend.create(os.environ["SMOKE_THREAD_KEY"], "amp", "amp")
    result = {
        "backend": backend.name,
        "sandbox_id": session.sandbox_id,
        "thread_key": session.thread_key,
    }
    try:
        result["status"] = await backend.status(session)
        exit_code, output = await backend.exec_run(
            session.sandbox_id,
            ["sh", "-lc", "echo exec-ok"],
            user="agent",
        )
        result["exec_exit_code"] = exit_code
        result["exec_output"] = output.decode("utf-8", errors="replace").strip()

        await backend.attach(session, logs=True)
        rt = _get_runtime(session.sandbox_id)
        result["attach_open"] = bool(rt.stdout_stream is not None and rt.stdin_stream is not None)

        await backend.write_stdin(
            session,
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Reply with exactly PONG and nothing else."}],
                },
            },
        )
        result["stdin_write_ok"] = True

        try:
            result["first_stdout_line"] = await asyncio.wait_for(
                anext(backend.stream_stdout(session)),
                timeout=20,
            )
        except TimeoutError:
            result["first_stdout_line"] = None
    finally:
        with contextlib.suppress(Exception):
            await backend.close_streams(session)
        with contextlib.suppress(Exception):
            await backend.stop(session)
        with contextlib.suppress(Exception):
            result["post_cleanup_status"] = await backend.status_by_id(session.sandbox_id)
        _drop_runtime(session.sandbox_id)

    print(json.dumps(result))

    if backend.name != "kubernetes":
        raise SystemExit("expected kubernetes backend")
    if result.get("status") != "running":
        raise SystemExit("sandbox pod did not reach running state")
    if result.get("exec_exit_code") != 0 or result.get("exec_output") != "exec-ok":
        raise SystemExit("exec_run verification failed")
    if not result.get("attach_open"):
        raise SystemExit("attach did not open stdin/stdout streams")
    if not result.get("stdin_write_ok"):
        raise SystemExit("stdin write failed")
    if result.get("post_cleanup_status") not in {"gone", "stopped", None}:
        raise SystemExit("sandbox cleanup failed")


asyncio.run(main())
PY
/app/.venv/bin/python /tmp/smoke_k8s_backend.py
'
