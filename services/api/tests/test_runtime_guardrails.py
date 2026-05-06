from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

_TOK = "test-secrets-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_TOK}"}


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses: dict[str, _FakeResponse | Exception]):
        self._responses = responses
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers: dict[str, str] | None = None):
        self.calls.append((url, headers))
        response = self._responses[url]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def reset_runtime_credential_cache() -> None:
    from api.runtime_guardrails import reset_runtime_credential_cache

    reset_runtime_credential_cache()
    yield
    reset_runtime_credential_cache()


@pytest.mark.asyncio
async def test_check_runtime_credentials_skipped_when_guard_disabled() -> None:
    from api.runtime_guardrails import check_runtime_credentials

    with patch.dict(
        "os.environ",
        {
            "RUNTIME_CREDENTIAL_GUARD_ENABLED": "0",
            "REQUIRED_RUNTIME_SECRET_KEYS": "AMP_API_KEY",
        },
        clear=True,
    ):
        report = await check_runtime_credentials()

    assert report["enabled"] is False
    assert report["status"] == "skipped"
    assert report["required_keys"] == ["AMP_API_KEY"]
    assert report["probe_keys"] == []
    assert report["invalid_keys"] == []


@pytest.mark.asyncio
async def test_check_runtime_credentials_ok_when_key_present() -> None:
    from api.runtime_guardrails import check_runtime_credentials

    base = "http://secrets:8100"
    url = f"{base}/secrets/AMP_API_KEY"
    fake_client = _FakeClient({url: _FakeResponse(200, {"value": "abc123"})})

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "AMP_API_KEY",
                "OPENAI_API_KEY": "ambient-provider-env-is-not-probed",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        report = await check_runtime_credentials()

    assert report["enabled"] is True
    assert report["status"] == "ok"
    assert report["checked_keys"] == ["AMP_API_KEY"]
    assert report["probe_keys"] == []
    assert report["invalid_keys"] == []
    assert report["key_lengths"] == {"AMP_API_KEY": 6}
    assert fake_client.calls == [(url, _AUTH_HEADERS)]


@pytest.mark.asyncio
async def test_check_runtime_credentials_sends_secrets_auth_token() -> None:
    from api.runtime_guardrails import check_runtime_credentials

    base = "http://secrets:8100"
    url = f"{base}/secrets/AMP_API_KEY"
    fake_client = _FakeClient({url: _FakeResponse(200, {"value": "abc123"})})

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "REQUIRED_RUNTIME_SECRET_KEYS": "AMP_API_KEY",
                "SECRET_MANAGER_URL": base,
                "SECRETS_AUTH_TOKEN": "tok-abc",
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        report = await check_runtime_credentials()

    assert report["status"] == "ok"
    assert fake_client.calls == [(url, {"Authorization": "Bearer tok-abc"})]


@pytest.mark.asyncio
async def test_check_runtime_credentials_marks_openai_key_invalid_on_401() -> None:
    from api.runtime_guardrails import check_runtime_credentials

    base = "http://secrets:8100"
    secret_url = f"{base}/secrets/OPENAI_API_KEY"
    probe_url = "https://api.openai.com/v1/models"
    fake_client = _FakeClient(
        {
            secret_url: _FakeResponse(200, {"value": "sk-live-valid-format"}),
            probe_url: _FakeResponse(401, {"error": {"message": "Incorrect API key"}}),
        }
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "OPENAI_API_KEY",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        report = await check_runtime_credentials()

    assert report["status"] == "failed"
    assert report["missing_keys"] == []
    assert report["invalid_keys"] == ["OPENAI_API_KEY"]
    assert report["probe_keys"] == ["OPENAI_API_KEY"]
    assert report["keys"]["OPENAI_API_KEY"] == {
        "status": "invalid",
        "length": 20,
        "provider": "openai",
        "probe_status": "invalid",
        "probe_http_status": 401,
    }
    assert fake_client.calls == [
        (secret_url, _AUTH_HEADERS),
        (probe_url, {"Authorization": "Bearer sk-live-valid-format"}),
    ]


@pytest.mark.asyncio
async def test_check_runtime_credentials_marks_anthropic_key_invalid_on_403() -> None:
    from api.runtime_guardrails import check_runtime_credentials

    base = "http://secrets:8100"
    secret_url = f"{base}/secrets/ANTHROPIC_API_KEY"
    probe_url = "https://api.anthropic.com/v1/models"
    fake_client = _FakeClient(
        {
            secret_url: _FakeResponse(200, {"value": "sk-ant-api03-valid-format"}),
            probe_url: _FakeResponse(403, {"error": {"message": "forbidden"}}),
        }
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "ANTHROPIC_API_KEY",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        report = await check_runtime_credentials()

    assert report["status"] == "failed"
    assert report["invalid_keys"] == ["ANTHROPIC_API_KEY"]
    assert report["keys"]["ANTHROPIC_API_KEY"] == {
        "status": "invalid",
        "length": 25,
        "provider": "anthropic",
        "probe_status": "invalid",
        "probe_http_status": 403,
    }
    assert fake_client.calls == [
        (secret_url, _AUTH_HEADERS),
        (
            probe_url,
            {
                "x-api-key": "sk-ant-api03-valid-format",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_check_runtime_credentials_degrades_on_transient_provider_error() -> None:
    from api.runtime_guardrails import check_runtime_credentials

    base = "http://secrets:8100"
    secret = "sk-live-secret-value"
    secret_url = f"{base}/secrets/OPENAI_API_KEY"
    probe_url = "https://api.openai.com/v1/models"
    fake_client = _FakeClient(
        {
            secret_url: _FakeResponse(200, {"value": secret}),
            probe_url: httpx.ConnectError(f"network failed for {secret}"),
        }
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "OPENAI_API_KEY",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        report = await check_runtime_credentials()

    assert report["status"] == "degraded"
    assert report["missing_keys"] == []
    assert report["invalid_keys"] == []
    assert report["errors"] == []
    assert report["provider_probe_errors"] == ["OPENAI_API_KEY:probe_request_failed:ConnectError"]
    assert secret not in str(report)


@pytest.mark.asyncio
async def test_check_runtime_credentials_uses_cache_for_provider_probe() -> None:
    from api.runtime_guardrails import check_runtime_credentials

    base = "http://secrets:8100"
    secret_url = f"{base}/secrets/OPENAI_API_KEY"
    probe_url = "https://api.openai.com/v1/models"
    fake_client = _FakeClient(
        {
            secret_url: _FakeResponse(200, {"value": "sk-live-valid-format"}),
            probe_url: _FakeResponse(200, {"data": []}),
        }
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "OPENAI_API_KEY",
                "RUNTIME_CREDENTIAL_CHECK_CACHE_SECONDS": "60",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        first = await check_runtime_credentials()
        second = await check_runtime_credentials()

    assert first == second
    assert fake_client.calls == [
        (secret_url, _AUTH_HEADERS),
        (probe_url, {"Authorization": "Bearer sk-live-valid-format"}),
    ]


@pytest.mark.asyncio
async def test_assert_runtime_credentials_ready_allows_transient_provider_error() -> None:
    from api.runtime_guardrails import assert_runtime_credentials_ready

    base = "http://secrets:8100"
    secret_url = f"{base}/secrets/OPENAI_API_KEY"
    probe_url = "https://api.openai.com/v1/models"
    fake_client = _FakeClient(
        {
            secret_url: _FakeResponse(200, {"value": "sk-live-secret-value"}),
            probe_url: httpx.ReadTimeout("provider timed out"),
        }
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "OPENAI_API_KEY",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        await assert_runtime_credentials_ready()


@pytest.mark.asyncio
async def test_assert_runtime_credentials_ready_raises_when_missing() -> None:
    from api.runtime_guardrails import assert_runtime_credentials_ready

    base = "http://secrets:8100"
    url = f"{base}/secrets/AMP_API_KEY"

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "AMP_API_KEY",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=_FakeClient({url: _FakeResponse(404, {"error": "not found"})}),
        ),
    ):
        with pytest.raises(RuntimeError, match="runtime credential guard failed"):
            await assert_runtime_credentials_ready()


@pytest.mark.asyncio
async def test_assert_runtime_credentials_ready_raises_when_provider_key_invalid() -> None:
    from api.runtime_guardrails import assert_runtime_credentials_ready

    base = "http://secrets:8100"
    secret_url = f"{base}/secrets/OPENAI_API_KEY"
    probe_url = "https://api.openai.com/v1/models"
    fake_client = _FakeClient(
        {
            secret_url: _FakeResponse(200, {"value": "sk-live-valid-format"}),
            probe_url: _FakeResponse(401, {"error": {"message": "Incorrect API key"}}),
        }
    )

    with (
        patch.dict(
            "os.environ",
            {
                "RUNTIME_CREDENTIAL_GUARD_ENABLED": "1",
                "SECRETS_AUTH_TOKEN": _TOK,
                "REQUIRED_RUNTIME_SECRET_KEYS": "OPENAI_API_KEY",
                "SECRET_MANAGER_URL": base,
            },
            clear=True,
        ),
        patch(
            "api.runtime_guardrails.httpx.AsyncClient",
            return_value=fake_client,
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="runtime credential guard failed invalid_keys=OPENAI_API_KEY",
        ):
            await assert_runtime_credentials_ready()
