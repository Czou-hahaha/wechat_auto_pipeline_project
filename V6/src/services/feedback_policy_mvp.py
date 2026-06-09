from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config import Settings

_CONFIRM_TOKEN = "APPLY_FEEDBACK_POLICY"


@dataclass
class PolicyRecommendation:
    id: str
    created_at: str
    window_days: int
    feedback_total: int
    by_category: dict[str, int]
    proposed_overrides: dict[str, Any]
    reasons: list[str]
    safe_to_apply: bool
    safety_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "window_days": self.window_days,
            "feedback_total": self.feedback_total,
            "by_category": self.by_category,
            "proposed_overrides": self.proposed_overrides,
            "reasons": self.reasons,
            "safe_to_apply": self.safe_to_apply,
            "safety_notes": self.safety_notes,
            "requires_manual_confirm_token": _CONFIRM_TOKEN,
        }


class FeedbackPolicyEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.data_dir = settings.data_path()
        self.feedback_path = self.data_dir / "feedback_events.json"
        self.rec_path = self.data_dir / "feedback_policy_recommendation.json"
        self.overrides_path = self._resolve_overrides_path()

    def _resolve_overrides_path(self) -> Path:
        raw = (self.settings.feedback_policy_overrides_path or "").strip()
        p = Path(raw).expanduser() if raw else Path("config/feedback_policy_overrides.json")
        if not p.is_absolute():
            p = Path.cwd() / p
        return p

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _feedback_window(self, window_days: int) -> list[dict[str, Any]]:
        rows = self._read_json(self.feedback_path, [])
        if not isinstance(rows, list):
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(window_days)))
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            created = str(row.get("created_at") or "").strip()
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                out.append(row)
        return out

    def recompute(self, *, window_days: int = 14) -> dict[str, Any]:
        rows = self._feedback_window(window_days)
        by_category: dict[str, int] = {}
        for row in rows:
            c = str(row.get("category") or "general").strip().lower()
            by_category[c] = by_category.get(c, 0) + 1

        current = self.settings.feedback_policy_overrides()
        proposed = dict(current)
        reasons: list[str] = []
        safety_notes: list[str] = []
        safe = True

        total = len(rows)
        factual = by_category.get("factual_error", 0)
        citation = by_category.get("citation_gap", 0)
        off_topic = by_category.get("off_topic", 0)
        style = by_category.get("style_issue", 0)

        if total < 3:
            safe = False
            safety_notes.append("最近反馈不足 3 条，跳过自动策略建议")

        base_threshold = int(current.get("qa_rewrite_pass_threshold", self.settings.qa_rewrite_pass_threshold))
        base_rounds = int(current.get("qa_rewrite_max_rounds", self.settings.qa_rewrite_max_rounds))
        base_prefilter = bool(current.get("search_prefilter_enabled", self.settings.search_prefilter_enabled))

        if factual >= 3:
            next_threshold = min(92, base_threshold + 2)
            proposed["qa_rewrite_pass_threshold"] = next_threshold
            reasons.append(f"factual_error={factual}，建议提高 QA 门槛到 {next_threshold}")
        if citation >= 3 or style >= 4:
            next_rounds = min(4, base_rounds + 1)
            proposed["qa_rewrite_max_rounds"] = next_rounds
            reasons.append(f"citation/style 问题累计，建议重写轮次到 {next_rounds}")
        if off_topic >= 3 and not base_prefilter:
            proposed["search_prefilter_enabled"] = True
            reasons.append("off_topic 反馈偏高，建议开启检索预过滤")

        if abs(int(proposed.get("qa_rewrite_pass_threshold", base_threshold)) - base_threshold) > 4:
            safe = False
            safety_notes.append("QA 阈值单次调整超过 4 分，触发安全拦截")
        if int(proposed.get("qa_rewrite_max_rounds", base_rounds)) - base_rounds > 1:
            safe = False
            safety_notes.append("重写轮次单次上调超过 1，触发安全拦截")

        rec = PolicyRecommendation(
            id=str(uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            window_days=int(window_days),
            feedback_total=total,
            by_category=by_category,
            proposed_overrides=proposed,
            reasons=reasons or ["暂无足够信号，不建议调整"],
            safe_to_apply=safe and bool(reasons),
            safety_notes=safety_notes,
        )
        self._write_json(self.rec_path, rec.to_dict())
        return rec.to_dict()

    def current_recommendation(self) -> dict[str, Any]:
        data = self._read_json(self.rec_path, {})
        return data if isinstance(data, dict) else {}

    def current_overrides(self) -> dict[str, Any]:
        return self.settings.feedback_policy_overrides()

    def apply(self, *, recommendation_id: str, confirm_token: str) -> dict[str, Any]:
        rec = self.current_recommendation()
        if not rec:
            raise ValueError("no recommendation")
        if str(rec.get("id") or "") != (recommendation_id or "").strip():
            raise ValueError("recommendation id mismatch")
        if (confirm_token or "").strip() != _CONFIRM_TOKEN:
            raise ValueError("confirm token invalid")
        if not bool(rec.get("safe_to_apply")):
            raise ValueError("recommendation blocked by safety checks")

        current = self.current_overrides()
        backup = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "overrides": current,
        }
        backup_path = self.data_dir / f"feedback_policy_overrides.backup.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        self._write_json(backup_path, backup)

        next_overrides = rec.get("proposed_overrides") or {}
        if not isinstance(next_overrides, dict):
            raise ValueError("invalid proposed overrides")
        self._write_json(self.overrides_path, next_overrides)
        return {
            "ok": True,
            "applied_overrides": next_overrides,
            "backup_path": str(backup_path),
        }

    def rollback(self, *, backup_path: str) -> dict[str, Any]:
        p = Path((backup_path or "").strip()).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        data = self._read_json(p, {})
        prev = data.get("overrides") if isinstance(data, dict) else None
        if not isinstance(prev, dict):
            raise ValueError("invalid backup")
        self._write_json(self.overrides_path, prev)
        return {"ok": True, "restored_overrides": prev}
