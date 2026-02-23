from __future__ import annotations

import asyncio
import time

import structlog

from .config import Settings
from .cursors import CursorStore
from .db import close_pool, create_pool
from .extractors.attio import AttioExtractor
from .extractors.base import BaseExtractor, ExtractResult
from .extractors.betterstack import BetterStackExtractor
from .extractors.github import GitHubExtractor
from .extractors.google import GoogleExtractor
from .extractors.granola import GranolaExtractor
from .extractors.linear import LinearExtractor
from .extractors.pylon import PylonExtractor
from .extractors.slack import SlackExtractor

log = structlog.get_logger()


def _build_extractors(settings: Settings) -> list[BaseExtractor]:
    extractors: list[BaseExtractor] = []

    if settings.pov_slack_token or settings.pov_slack_user_token:
        token = settings.pov_slack_user_token or settings.pov_slack_token
        extractors.append(SlackExtractor(token=token))

    if settings.pov_linear_api_key:
        extractors.append(LinearExtractor(api_key=settings.pov_linear_api_key))

    if settings.pov_github_token:
        extractors.append(GitHubExtractor(token=settings.pov_github_token))

    if settings.pov_google_client_id or settings.pov_google_service_account_key:
        extractors.append(
            GoogleExtractor(
                client_id=settings.pov_google_client_id,
                client_secret=settings.pov_google_client_secret,
                refresh_token=settings.pov_google_refresh_token,
                service_account_key=settings.pov_google_service_account_key,
            )
        )

    tokens = [settings.pov_granola_access_token]
    if settings.pov_granola_access_token_2:
        tokens.append(settings.pov_granola_access_token_2)
    tokens = [t for t in tokens if t]
    if tokens or settings.pov_granola_enterprise_api_key:
        extractors.append(
            GranolaExtractor(
                access_tokens=tokens,
                enterprise_api_key=settings.pov_granola_enterprise_api_key,
            )
        )

    if settings.pov_attio_api_key:
        extractors.append(AttioExtractor(api_key=settings.pov_attio_api_key))

    if settings.pov_pylon_api_token:
        extractors.append(PylonExtractor(api_token=settings.pov_pylon_api_token))

    if settings.pov_betterstack_api_token:
        extractors.append(
            BetterStackExtractor(api_token=settings.pov_betterstack_api_token)
        )

    return extractors


async def run_sync(
    settings: Settings | None = None,
    sources: list[str] | None = None,
) -> list[ExtractResult]:
    if settings is None:
        settings = Settings()

    pool = await create_pool(settings.database_url)
    cursors = CursorStore()

    try:
        extractors = _build_extractors(settings)
        if sources:
            extractors = [e for e in extractors if e.source in sources]

        if not extractors:
            log.warning("no_extractors_configured")
            return []

        results: list[ExtractResult] = []
        for extractor in extractors:
            log.info("extractor_start", source=extractor.source)
            start = time.monotonic()
            try:
                ok = await extractor.preflight()
                if not ok:
                    log.warning("extractor_preflight_failed", source=extractor.source)
                    continue

                result = await extractor.extract(pool, cursors)
                results.append(result)
                log.info(
                    "extractor_done",
                    source=result.source,
                    records=result.records_written,
                    kinds=result.kinds,
                    duration_ms=result.duration_ms,
                )
            except Exception as e:
                log.error(
                    "extractor_failed",
                    source=extractor.source,
                    error=str(e),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )

        return results
    finally:
        await close_pool(pool)


async def run_continuous(
    settings: Settings | None = None,
    interval: int | None = None,
) -> None:
    if settings is None:
        settings = Settings()
    sync_interval = interval or settings.sync_interval_seconds

    log.info("continuous_sync_start", interval=sync_interval)

    while True:
        try:
            results = await run_sync(settings)
            total = sum(r.records_written for r in results)
            log.info(
                "sync_cycle_complete",
                sources=len(results),
                total_records=total,
            )
        except Exception as e:
            log.error("sync_cycle_failed", error=str(e))

        log.info("sync_waiting", seconds=sync_interval)
        await asyncio.sleep(sync_interval)
