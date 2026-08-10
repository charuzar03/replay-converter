"""Browser-only Pyodide entry point. Not part of the showdown_stats package."""
from __future__ import annotations

import json
from typing import Any, Dict

from showdown_stats.parser import BattleParser


def parse_replay(content: str, battle_id: str, replay_url: str = "", metadata_json: str = "{}") -> str:
    metadata: Dict[str, Any] = json.loads(metadata_json) if metadata_json else {}
    payload: Dict[str, Any] = {"battle_id": battle_id, "pokemon_rows": [], "warnings": [], "error": None}
    try:
        result = BattleParser(debug=False).parse(
            content, battle_id=battle_id, replay_url=replay_url, metadata=metadata
        )
        payload["battle_id"] = result.battle_id
        payload["pokemon_rows"] = [row.to_csv_row() for row in result.pokemon_rows]
        payload["warnings"] = list(result.warnings)
    except Exception as exc:  # one bad replay must never kill the batch
        payload["error"] = f"{type(exc).__name__}: {exc}"
    return json.dumps(payload)
