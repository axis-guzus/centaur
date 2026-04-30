from __future__ import annotations

CREDENTIAL_HEADER_NAMES: frozenset[str] = frozenset({
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "anthropic-api-key",
    "x-goog-api-key",
    "x-browser-use-api-key",
    "x-cg-pro-api-key",
    "x-cg-demo-api-key",
    "x-auth-token",
    "x-access-token",
    "auth-token",
    "jwt",
    "cookie",
})

CREDENTIAL_HEADER_SUFFIXES: tuple[str, ...] = (
    "-api-key",
    "-apikey",
    "-secret",
    "-token",
    "-auth",
)


def is_credential_header(name: str) -> bool:
    """Return True if a header name is allowed to carry a credential placeholder."""
    normalized = name.lower()
    if normalized in CREDENTIAL_HEADER_NAMES:
        return True
    return normalized.startswith("x-") and any(
        normalized.endswith(suffix) for suffix in CREDENTIAL_HEADER_SUFFIXES
    )


def classify_proxy_error(
    *,
    host: str,
    path: str,
    status: int,
    response_content_type: str = "",
    response_text_sample: str = "",
) -> str | None:
    if status < 400:
        return None
    content_type = response_content_type.lower()
    if "text" in content_type or "json" in content_type:
        if "unsupported content type" in response_text_sample.lower():
            return "unsupported_content_type"
    if host == "ampcode.com" and path.startswith("/api/internal?uploadThread"):
        return "amp_upload_thread_400" if status == 400 else "amp_upload_thread_error"
    if host == "ampcode.com" and path.startswith("/api/internal?"):
        return f"amp_internal_{status}"
    if status in {401, 403}:
        return "auth_or_permission_error"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "upstream_5xx"
    if status == 400:
        return "bad_request"
    return "upstream_4xx"
