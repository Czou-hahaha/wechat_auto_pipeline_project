"""历史聚类 fixture → 阶段三脚本：仅测 hydrate / 时间戳逻辑（不连 PG）。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

_V3 = Path(__file__).resolve().parents[1]
_FIXTURE = _V3 / "tests/data/dedupe_runs/beijing"


@pytest.fixture
def work(tmp_path: Path) -> Path:
    d = tmp_path / "ee_work"
    shutil.copytree(_FIXTURE, d)
    return d


def test_hydrate_adds_missing_cluster_members(work: Path) -> None:
    from tests.integration.run_event_enhancement_fixture import hydrate_articles_from_event_map

    before = json.loads((work / "articles.json").read_text(encoding="utf-8"))
    maps = json.loads((work / "event_article_map.json").read_text(encoding="utf-8"))
    assert len(before) == 1
    assert len(maps) == 4

    n = hydrate_articles_from_event_map(work)
    assert n == 3

    after = json.loads((work / "articles.json").read_text(encoding="utf-8"))
    assert len(after) == 4
    urls = set()
    for a in after:
        urls.add(str(a.get("source_url") or "").strip())
        ru = str(a.get("resolved_url") or "").strip()
        if ru:
            urls.add(ru)
    for m in maps:
        assert str(m.get("source_url") or "").strip() in urls


def test_touch_updates_created_at(work: Path) -> None:
    from tests.integration.run_event_enhancement_fixture import (
        hydrate_articles_from_event_map,
        touch_event_ranking_timestamps,
    )

    hydrate_articles_from_event_map(work)
    touch_event_ranking_timestamps(work)
    ev = json.loads((work / "events.json").read_text(encoding="utf-8"))[0]
    arts = json.loads((work / "articles.json").read_text(encoding="utf-8"))
    assert "2026" in str(ev.get("created_at") or "")
    assert all("2026" in str(a.get("created_at") or "") for a in arts)
