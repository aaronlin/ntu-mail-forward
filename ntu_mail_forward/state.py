from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load_seen_uids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("seen_uids", []))


def save_seen_uids(path: Path, seen_uids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "seen_uids": sorted(seen_uids),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
