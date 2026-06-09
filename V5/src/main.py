from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings
from src.pipeline import PipelineRunner

V3_MAIN_INNER = "V3_MAIN_INNER"


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def push_today_drafts(local_date_raw: str) -> None:
    s = Settings()
    setup_logging(s.log_level)
    from datetime import date

    local_day: date | None = None
    raw = (local_date_raw or "").strip()
    if raw:
        local_day = date.fromisoformat(raw)
    stats = await PipelineRunner(s).push_today_summaries_to_wechat(local_date=local_day)
    logging.info(
        "push_today_drafts done: eligible=%d skipped_already=%d skipped_empty=%d skipped_outdated=%d skipped_qa=%d pushed=%d failed=%d",
        stats.eligible,
        stats.skipped_already,
        stats.skipped_empty,
        stats.skipped_outdated,
        stats.skipped_qa,
        stats.pushed,
        stats.failed,
    )


async def run_once() -> None:
    s = Settings()
    setup_logging(s.log_level)
    stats = await PipelineRunner(s).run_once()
    logging.info(
        "run_once done: candidates=%d published=%d staged_for_review=%d skipped_duplicate=%d skipped_policy=%d "
        "skipped_prefilter=%d skipped_summarize_cap=%d skipped_insufficient_articles=%d skipped_encoding=%d "
        "skipped_digest=%d skipped_too_short=%d skipped_summary_fallback=%d skipped_qa=%d failed=%d",
        stats.total_candidates,
        stats.published,
        stats.staged_for_review,
        stats.skipped_duplicate,
        stats.skipped_policy,
        stats.skipped_prefilter,
        stats.skipped_summarize_cap,
        stats.skipped_insufficient_articles,
        stats.skipped_encoding,
        stats.skipped_digest,
        stats.skipped_too_short,
        stats.skipped_summary_fallback,
        stats.skipped_qa,
        stats.failed,
    )


async def generate_event_press() -> None:
    """仅执行阶段四：根据当前 ``data/events.json`` + ``articles.json`` 写 ``event_press_zh``。"""
    s = Settings()
    setup_logging(s.log_level)
    from src.event_press_workflow import run_event_press_generation

    await run_event_press_generation(PipelineRunner(s).store, s, force=True)
    logging.info("generate-event-press done")


async def refresh_library_times(max_age_days: int, *, dry_run: bool = False) -> None:
    from src.library_time_refresh import refresh_library_published_at_and_prune

    s = Settings()
    setup_logging(s.log_level)
    stats = await refresh_library_published_at_and_prune(
        s, max_age_days=max_age_days, dry_run=dry_run
    )
    logging.info(
        "refresh-library-times done: total=%d refreshed=%d fetch_failed=%d kept=%d "
        "removed_missing_time=%d removed_time_window=%d dry_run=%s max_age_days=%d",
        stats.total,
        stats.refreshed,
        stats.fetch_failed,
        stats.kept,
        stats.removed_missing_time,
        stats.removed_time_window,
        dry_run,
        max_age_days,
    )


def clean_library() -> None:
    s = Settings()
    setup_logging(s.log_level)
    stats = PipelineRunner(s).clean_library_strict()
    logging.info(
        "clean_library done: total=%d kept=%d removed=%d missing_time=%d time_window=%d "
        "scope=%d policy=%d low_relevance=%d digest=%d too_short=%d",
        stats.total,
        stats.kept,
        stats.removed,
        stats.removed_missing_time,
        stats.removed_time_window,
        stats.removed_scope,
        stats.removed_policy,
        stats.removed_low_relevance,
        stats.removed_digest,
        stats.removed_too_short,
    )


async def scan_data_sources_health() -> None:
    from src.bff.data_source_health_store import run_full_health_scan

    summary = await run_full_health_scan()
    s = summary.get("summary") or {}
    logging.info(
        "data source health scan done: total=%s ok=%s failed=%s needs_attention=%s",
        s.get("total"),
        s.get("ok"),
        s.get("failed"),
        s.get("needs_attention"),
    )


def run_scheduler() -> None:
    from src.bff.schedule_config import load_scheduler_jobs, scheduler_timezone

    s = Settings()
    setup_logging(s.log_level)
    jobs = load_scheduler_jobs()
    if not jobs:
        raise ValueError("定时采集未启用或未配置任务（见 config/schedule_jobs.json）")
    tz = scheduler_timezone()
    sched = BlockingScheduler(timezone=tz)

    def _job() -> None:
        asyncio.run(run_once())

    def _health_job() -> None:
        asyncio.run(scan_data_sources_health())

    labels: list[str] = []
    for job in jobs:
        jid = str(job.get("id") or "").strip() or f"job_{len(labels)}"
        hour = int(job.get("hour", 8))
        minute = int(job.get("minute", 0))
        sched.add_job(
            _job,
            CronTrigger(hour=hour, minute=minute),
            id=jid,
            replace_existing=True,
        )
        labels.append(f"{job.get('label', jid)} {hour:02d}:{minute:02d}")

    if s.data_source_health_weekly_enabled:
        dow = (s.data_source_health_weekly_dow or "mon").strip().lower()
        h = int(s.data_source_health_weekly_hour)
        m = int(s.data_source_health_weekly_minute)
        sched.add_job(
            _health_job,
            CronTrigger(day_of_week=dow, hour=h, minute=m),
            id="job_data_source_health_weekly",
            replace_existing=True,
        )
        labels.append(f"数据源周检 {dow} {h:02d}:{m:02d}")

    logging.info("scheduler started (%s): %s", tz, " | ".join(labels))
    sched.start()


def _execute_cli() -> None:
    parser = argparse.ArgumentParser(description="RSS 聚合 + GDELT 检索 -> 摘要 -> 公众号草稿箱")
    parser.add_argument(
        "command",
        choices=[
            "run-once",
            "run-scheduler",
            "push-today-drafts",
            "clean-library",
            "refresh-library-times",
            "generate-event-press",
            "scan-data-sources",
            "run-bff",
        ],
    )
    parser.add_argument(
        "--local-date",
        default="",
        metavar="YYYY-MM-DD",
        help="仅 push-today-drafts：按本地日筛选 created_at（默认今天，时区见 SCHEDULE_TIMEZONE）",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=7,
        help="refresh-library-times：保留 source_published_at 在最近 N 天内的文章（默认 7）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="refresh-library-times：只统计不落盘",
    )
    args = parser.parse_args()
    if args.command == "run-once":
        asyncio.run(run_once())
    elif args.command == "run-scheduler":
        run_scheduler()
    elif args.command == "clean-library":
        clean_library()
    elif args.command == "refresh-library-times":
        asyncio.run(refresh_library_times(args.max_age_days, dry_run=args.dry_run))
    elif args.command == "generate-event-press":
        asyncio.run(generate_event_press())
    elif args.command == "scan-data-sources":
        asyncio.run(scan_data_sources_health())
    elif args.command == "run-bff":
        import uvicorn

        host = os.environ.get("BFF_HOST", "127.0.0.1")
        port = int(os.environ.get("BFF_PORT", "8787"))
        uvicorn.run("src.bff.app:app", host=host, port=port, reload=False)
    else:
        asyncio.run(push_today_drafts(args.local_date))


def main() -> None:
    setup_logging(Settings().log_level)
    if os.environ.get(V3_MAIN_INNER) == "1":
        _execute_cli()
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("run-once", "push-today-drafts"):
        env = os.environ.copy()
        env[V3_MAIN_INNER] = "1"
        last_code = 1
        for attempt in range(1, 4):
            logging.warning(
                "subprocess retry wrapper: command=%s attempt=%d/3",
                sys.argv[1],
                attempt,
            )
            proc = subprocess.run([sys.executable, "-m", "src.main", *sys.argv[1:]], env=env)
            last_code = proc.returncode
            if last_code == 0:
                sys.exit(0)
            logging.error(
                "subprocess exited with code=%s (attempt %d/3). Retrying if attempts remain.",
                last_code,
                attempt,
            )
        logging.error(
            "command=%s failed after 3 subprocess attempts; last_exit_code=%s. See logs above.",
            sys.argv[1],
            last_code,
        )
        sys.exit(last_code if last_code else 1)
    _execute_cli()


if __name__ == "__main__":
    main()
