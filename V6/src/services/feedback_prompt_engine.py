"""Feedback aggregation → Prompt Contract suggestions (V6)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config import Settings
from src.services.feedback_policy_mvp import FeedbackPolicyEngine, _CONFIRM_TOKEN
from src.services.prompt_contract_mvp import PromptContractStore

_CATEGORY_PROMPT_RULES: dict[str, dict[str, list[str]]] = {
    "factual_error": {
        "hard_rules": ["禁止补充材料中未出现的事实、数据或政策表述；冲突以原文为准。"],
        "soft_rules": [],
    },
    "citation_gap": {
        "hard_rules": ["通稿关键事实句须带〔n〕阅读引用，且 n 对应参考稿序号。"],
        "soft_rules": ["重写时优先补齐缺失的〔n〕锚点。"],
    },
    "grounding": {
        "hard_rules": ["禁止补充材料中未出现的事实、数据或政策表述；冲突以原文为准。"],
        "soft_rules": [],
    },
    "style_issue": {
        "hard_rules": [],
        "soft_rules": ["段落首句先给结论；避免空泛套话与重复表述。"],
    },
    "off_topic": {
        "hard_rules": ["离题战争/娱乐/拼盘快讯一律不得作为低空经济主焦点写入通稿。"],
        "soft_rules": [],
    },
    "missing_context": {
        "hard_rules": [],
        "soft_rules": ["国内参照须来自素材；无国内稿时不强行编造对标政策。"],
    },
}


class FeedbackPromptEngine(FeedbackPolicyEngine):
    """Extends policy recompute with prompt_contract diff suggestions."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._prompt_suggestion_path = self.data_dir / "feedback_prompt_suggestion.json"
        self._contract = PromptContractStore(settings.data_path())

    def _feedback_rows(self, window_days: int) -> list[dict[str, Any]]:
        return self._feedback_window(window_days)

    def _dedupe_rules(self, rules: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for r in rules:
            s = str(r).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    def recompute_prompt_suggestions(self, *, window_days: int = 14) -> dict[str, Any]:
        policy_rec = self.recompute(window_days=window_days)
        rows = self._feedback_rows(window_days)
        by_category: dict[str, int] = {}
        for row in rows:
            c = str(row.get("category") or "general").strip().lower()
            by_category[c] = by_category.get(c, 0) + 1

        current = self._contract.get_editable()
        cur_hard = list(current.get("hard_rules") or [])
        cur_soft = list(current.get("soft_rules") or [])

        add_hard: list[str] = []
        add_soft: list[str] = []
        reasons: list[str] = []

        for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
            if count < 2:
                continue
            mapping = _CATEGORY_PROMPT_RULES.get(cat, {})
            for rule in mapping.get("hard_rules") or []:
                if rule not in cur_hard and rule not in add_hard:
                    add_hard.append(rule)
                    reasons.append(f"{cat}×{count} → hard_rule")
            for rule in mapping.get("soft_rules") or []:
                if rule not in cur_soft and rule not in add_soft:
                    add_soft.append(rule)
                    reasons.append(f"{cat}×{count} → soft_rule")

        proposed_contract = {
            "objective": current.get("objective") or "",
            "hard_rules": self._dedupe_rules(cur_hard + add_hard),
            "soft_rules": self._dedupe_rules(cur_soft + add_soft),
        }

        payload = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "window_days": window_days,
            "feedback_total": len(rows),
            "by_category": by_category,
            "policy_recommendation": policy_rec,
            "current_contract": {"hard_rules": cur_hard, "soft_rules": cur_soft},
            "proposed_contract": proposed_contract,
            "additions": {"hard_rules": add_hard, "soft_rules": add_soft},
            "reasons": reasons or ["暂无足够反馈生成 Prompt 建议"],
            "safe_to_apply": bool(add_hard or add_soft) and len(rows) >= 3,
            "requires_manual_confirm_token": _CONFIRM_TOKEN,
        }
        self._write_json(self._prompt_suggestion_path, payload)
        return payload

    def current_prompt_suggestion(self) -> dict[str, Any]:
        data = self._read_json(self._prompt_suggestion_path, {})
        return data if isinstance(data, dict) else {}

    def apply_prompt_suggestion(self, *, suggestion_id: str, confirm_token: str) -> dict[str, Any]:
        rec = self.current_prompt_suggestion()
        if not rec:
            raise ValueError("no prompt suggestion")
        if str(rec.get("id") or "") != (suggestion_id or "").strip():
            raise ValueError("suggestion id mismatch")
        if (confirm_token or "").strip() != _CONFIRM_TOKEN:
            raise ValueError("confirm token invalid")
        if not bool(rec.get("safe_to_apply")):
            raise ValueError("suggestion blocked")

        proposed = rec.get("proposed_contract") or {}
        if not isinstance(proposed, dict):
            raise ValueError("invalid proposed contract")

        backup = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "contract": self._contract.get_editable(),
        }
        backup_path = self.data_dir / f"prompt_contract.backup.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        self._write_json(backup_path, backup)
        saved = self._contract.put_editable(proposed)
        return {"ok": True, "contract": saved, "backup_path": str(backup_path)}

    def rollback_prompt(self, *, backup_path: str) -> dict[str, Any]:
        p = Path((backup_path or "").strip()).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        data = self._read_json(p, {})
        prev = data.get("contract") if isinstance(data, dict) else None
        if not isinstance(prev, dict):
            raise ValueError("invalid backup")
        restored = self._contract.put_editable(prev)
        return {"ok": True, "contract": restored}

    def summary_with_prompt(self, *, window_days: int = 14) -> dict[str, Any]:
        from src.services.feedback_loop_mvp import FeedbackStore

        base = FeedbackStore(self.data_dir).summary()
        return {
            **base,
            "promptSuggestion": self.current_prompt_suggestion(),
            "policyRecommendation": self.current_recommendation(),
            "windowDays": window_days,
        }
