from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlparse


def _host(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        return (urlparse(raw).netloc or "").lower()
    except Exception:
        return ""


def _extract_entities(event_row: dict[str, Any], article_rows: list[dict[str, Any]]) -> list[str]:
    entities: list[str] = []
    ev_title = str(event_row.get("title_zh") or event_row.get("title") or "").strip()
    if ev_title:
        entities.append(ev_title[:48])
    for row in article_rows[:6]:
        title = str(row.get("title") or "").strip()
        if title:
            entities.append(title[:48])
    out: list[str] = []
    seen: set[str] = set()
    for item in entities:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out[:8]


def build_event_map_payload(event_row: dict[str, Any], article_rows: list[dict[str, Any]]) -> dict[str, Any]:
    event_id = str(event_row.get("id") or "").strip()
    title = str(event_row.get("title_zh") or event_row.get("title") or "未命名事件").strip()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    source_hosts: Counter[str] = Counter()

    nodes.append(
        {
            "id": f"event:{event_id}",
            "type": "event",
            "label": title,
        }
    )

    for idx, row in enumerate(article_rows, start=1):
        url = str(row.get("resolved_url") or row.get("source_url") or "").strip()
        if not url:
            continue
        host = _host(url)
        if host:
            source_hosts[host] += 1
        article_node_id = f"article:{event_id}:{idx}"
        nodes.append(
            {
                "id": article_node_id,
                "type": "article",
                "label": str(row.get("title") or "untitled")[:72],
                "host": host,
                "url": url,
            }
        )
        edges.append(
            {
                "source": article_node_id,
                "target": f"event:{event_id}",
                "relation": "supports",
            }
        )
        snippet = str(row.get("summary") or row.get("extracted_text") or "").strip()
        if snippet:
            evidence.append(
                {
                    "sourceHost": host,
                    "articleTitle": str(row.get("title") or "").strip(),
                    "url": url,
                    "snippet": snippet[:220],
                }
            )

    for entity in _extract_entities(event_row, article_rows):
        entity_id = f"entity:{event_id}:{len(nodes)}"
        nodes.append({"id": entity_id, "type": "entity", "label": entity})
        edges.append(
            {
                "source": f"event:{event_id}",
                "target": entity_id,
                "relation": "mentions",
            }
        )

    return {
        "eventId": event_id,
        "title": title,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "sourceDiversity": len(source_hosts),
        "topSources": [{"host": k, "count": v} for k, v in source_hosts.most_common(8)],
        "nodes": nodes,
        "edges": edges,
        "evidence": evidence[:20],
    }
