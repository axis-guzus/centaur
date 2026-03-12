from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from api.deps import verify_operator_api_key
from api.metrics import CONTENT_TYPE_LATEST, render_metrics

router = APIRouter()


@router.get("/health")
@router.get("/health/ready")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> Response:
    from api.app import app

    payload = await render_metrics(app.state.db_pool)
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


@router.get("/health/tools", dependencies=[Depends(verify_operator_api_key)])
async def health_tools() -> dict[str, Any]:
    from api.app import get_tool_manager

    tool_manager = get_tool_manager()
    loaded = [
        {"name": tool.name, "methods": sorted(method.method_name for method in tool.methods)}
        for tool in tool_manager.tools.values()
    ]
    failed = list(tool_manager.load_failures)
    return {
        "loaded": loaded,
        "failed": failed,
        "summary": {
            "loaded_count": len(loaded),
            "failed_count": len(failed),
            "total_methods": sum(len(item["methods"]) for item in loaded),
        },
    }
