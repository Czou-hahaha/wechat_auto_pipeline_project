from __future__ import annotations

import argparse
import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings
from src.pipeline import PipelineRunner


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


async def run_once() -> None:
    s = Settings()
    setup_logging(s.log_level)
    stats = await PipelineRunner(s).run_once()
    logging.info(
        "run_once done: candidates=%d published=%d skipped_duplicate=%d failed=%d",
        stats.total_candidates,
        stats.published,
        stats.skipped_duplicate,
        stats.failed,
    )


def run_scheduler() -> None:
    s = Settings()
    setup_logging(s.log_level)
    if not s.schedule_enabled:
        raise ValueError("SCHEDULE_ENABLED=false，无法启动定时任务")
    sched = BlockingScheduler(timezone=s.schedule_timezone)

    def _job() -> None:
        asyncio.run(run_once())

    sched.add_job(_job, CronTrigger(hour=s.schedule_morning_hour, minute=0), id="morning", replace_existing=True)
    sched.add_job(_job, CronTrigger(hour=s.schedule_evening_hour, minute=0), id="evening", replace_existing=True)
    logging.info("scheduler started at %02d:00 and %02d:00 (%s)", s.schedule_morning_hour, s.schedule_evening_hour, s.schedule_timezone)
    sched.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="定时搜索 -> 摘要 -> 公众号草稿箱")
    parser.add_argument("command", choices=["run-once", "run-scheduler"])
    args = parser.parse_args()
    if args.command == "run-once":
        asyncio.run(run_once())
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
