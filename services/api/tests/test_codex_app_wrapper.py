from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


WRAPPER_PY = Path(__file__).resolve().parents[2] / "sandbox" / "codex-app-wrapper.py"


def _load_wrapper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("codex_app_wrapper", WRAPPER_PY)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configure_laminar_otel_uses_turn_trace_id(monkeypatch) -> None:
    wrapper = _load_wrapper()
    writes: list[tuple[str, object]] = []

    def fake_request(method: str, params: dict, timeout: float = 30.0) -> dict:
        assert method == "config/value/write"
        writes.append((params["keyPath"], params["value"]))
        return {}

    monkeypatch.setattr(wrapper, "request", fake_request)
    monkeypatch.setenv("CENTAUR_TRACE_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("CENTAUR_THREAD_KEY", "warm-placeholder")
    monkeypatch.setenv("LMNR_BASE_URL", "http://laminar:8000")
    monkeypatch.setenv("LMNR_PROJECT_API_KEY", "lmnr-key")
    monkeypatch.setenv("CODEX_OTEL_ENVIRONMENT", "staging")

    wrapper._configure_laminar_otel(
        "00000000-0000-0000-0000-000000000123",
        "slack:C123:1700000000.000100",
    )

    indexed = dict(writes)
    assert indexed["otel.environment"] == "staging"
    assert (
        indexed["otel.trace_exporter.otlp-http.endpoint"]
        == "http://laminar:8000/v1/traces"
    )
    assert indexed["otel.trace_exporter.otlp-http.protocol"] == "binary"
    assert indexed["otel.trace_exporter.otlp-http.headers"] == {
        "x-trace-id": "00000000-0000-0000-0000-000000000123",
        "x-centaur-thread-key": "slack:C123:1700000000.000100",
        "authorization": "Bearer lmnr-key",
    }
