from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class MailRecord:
    uid: str
    message_number: int | None = None
    sender: str = ""
    subject: str = ""
    date: str = ""
    decision: str = ""
    reason: str = ""
    processed_at: str = ""
    forwarded_at: str = ""
    delete_after: str = ""
    deleted_at: str = ""
    error: str = ""


@dataclass
class MailState:
    records: dict[str, MailRecord]
    updated_at: str = ""


def load_seen_uids(path: Path) -> set[str]:
    return set(load_state(path).records)


def save_seen_uids(path: Path, seen_uids: set[str]) -> None:
    now = utc_now()
    state = MailState(
        records={
            uid: MailRecord(uid=uid, decision="seen", reason="initialized", processed_at=now)
            for uid in seen_uids
        },
        updated_at=now,
    )
    save_state(path, state)


def load_state(path: Path) -> MailState:
    if not path.exists():
        return MailState(records={})

    data = json.loads(path.read_text(encoding="utf-8"))
    if "records" in data:
        records = {
            uid: MailRecord(**{"uid": uid, **record})
            for uid, record in data.get("records", {}).items()
        }
        return MailState(records=records, updated_at=str(data.get("updated_at", "")))

    now = str(data.get("updated_at", "")) or utc_now()
    records = {
        uid: MailRecord(
            uid=uid,
            decision="legacy_seen",
            reason="migrated from seen_uids",
            processed_at=now,
        )
        for uid in data.get("seen_uids", [])
    }
    return MailState(records=records, updated_at=now)


def save_state(path: Path, state: MailState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    updated_at = utc_now()
    payload = {
        "updated_at": updated_at,
        "records": {
            uid: _record_payload(record)
            for uid, record in sorted(state.records.items())
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_payload(record: MailRecord) -> dict[str, object]:
    payload = asdict(record)
    payload.pop("uid", None)
    return payload
