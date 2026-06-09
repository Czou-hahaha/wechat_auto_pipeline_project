from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from src.storage import JsonStore


def _dt(raw: str) -> datetime:
    s = (raw or "").strip()
    if not s:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _title_similarity(a: str, b: str) -> float:
    x = (a or "").strip().lower()
    y = (b or "").strip().lower()
    if not x or not y:
        return 0.0
    return SequenceMatcher(None, x, y).ratio()


def _event_title(event: dict[str, Any]) -> str:
    return str(event.get("title_zh") or event.get("title") or "").strip()


@dataclass
class _Candidate:
    event_id: str
    title: str
    created_at: str
    dominant_topic_key: str
    relation: str
    score: float


def build_event_history_payload(store: JsonStore, event_id: str) -> dict[str, Any]:
    target = store.get_event(event_id)
    if not target:
        raise ValueError("event not found")

    target_topic = str(target.get("dominant_topic_key") or "").strip().lower()
    target_title = _event_title(target)
    target_time = _dt(str(target.get("created_at") or ""))

    cands: list[_Candidate] = []
    for row in store.list_events():
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id") or "").strip()
        if not eid or eid == event_id:
            continue
        title = _event_title(row)
        topic = str(row.get("dominant_topic_key") or "").strip().lower()
        sim = _title_similarity(target_title, title)
        same_topic = bool(target_topic and topic and target_topic == topic)
        if same_topic or sim >= 0.58:
            rel = "same_topic" if same_topic else "semantic_neighbor"
            score = 0.85 if same_topic else sim
            cands.append(
                _Candidate(
                    event_id=eid,
                    title=title,
                    created_at=str(row.get("created_at") or ""),
                    dominant_topic_key=topic,
                    relation=rel,
                    score=score,
                )
            )

    cands.sort(key=lambda x: (_dt(x.created_at), -x.score))
    prev_events = [x for x in cands if _dt(x.created_at) <= target_time][-6:]
    next_events = [x for x in cands if _dt(x.created_at) > target_time][:6]

    chain = prev_events + [
        _Candidate(
            event_id=event_id,
            title=target_title,
            created_at=str(target.get("created_at") or ""),
            dominant_topic_key=target_topic,
            relation="current",
            score=1.0,
        )
    ] + next_events
    chain.sort(key=lambda x: _dt(x.created_at))

    lines: list[str] = []
    if chain:
        lines.append("该事件主线可分为以下阶段：")
        for idx, item in enumerate(chain, start=1):
            stamp = item.created_at[:10] if item.created_at else "未知时间"
            flag = "（当前）" if item.event_id == event_id else ""
            lines.append(f"{idx}. {stamp} {item.title}{flag}")
        lines.append("从时间线看，议题由早期通报逐步转向规则执行与落地反馈。")
    report = "\n".join(lines)

    return {
        "eventId": event_id,
        "currentTitle": target_title,
        "chain": [
            {
                "eventId": x.event_id,
                "title": x.title,
                "createdAt": x.created_at,
                "relation": x.relation,
                "score": round(float(x.score), 3),
            }
            for x in chain
        ],
        "timelineReport": report,
    }
