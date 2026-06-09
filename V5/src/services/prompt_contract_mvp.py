from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PromptContractStore:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "prompt_contract.json"

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get_editable(self) -> dict[str, Any]:
        raw = self._read()
        hard_rules = raw.get("hard_rules")
        soft_rules = raw.get("soft_rules")
        # Backward compatibility: old payload only had hard_rules list[str].
        if not isinstance(hard_rules, list):
            hard_rules = []
        if not isinstance(soft_rules, list):
            soft_rules = []
        return {
            "objective": str(raw.get("objective") or "").strip(),
            "hard_rules": [str(x).strip() for x in hard_rules if str(x).strip()],
            "soft_rules": [str(x).strip() for x in soft_rules if str(x).strip()],
        }

    def put_editable(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload must be object")
        objective = str(payload.get("objective") or "").strip()
        hard_rules_raw = payload.get("hard_rules")
        soft_rules_raw = payload.get("soft_rules")
        if not objective:
            raise ValueError("objective is required")
        if not isinstance(hard_rules_raw, list):
            raise ValueError("hard_rules must be list")
        if soft_rules_raw is None:
            soft_rules_raw = []
        if not isinstance(soft_rules_raw, list):
            raise ValueError("soft_rules must be list")
        hard_rules = [str(x).strip() for x in hard_rules_raw if str(x).strip()]
        soft_rules = [str(x).strip() for x in soft_rules_raw if str(x).strip()]
        if not hard_rules:
            raise ValueError("hard_rules is required")
        out = {
            "objective": objective,
            "hard_rules": hard_rules,
            "soft_rules": soft_rules,
        }
        self._write(out)
        return out
