from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ntu_mail_forward.state import MailRecord, MailState, load_state, save_state


class StateTest(unittest.TestCase):
    def test_migrates_seen_uids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"seen_uids": ["a", "b"]}), encoding="utf-8")

            state = load_state(path)

        self.assertEqual(set(state.records), {"a", "b"})
        self.assertEqual(state.records["a"].decision, "legacy_seen")

    def test_round_trips_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            record = MailRecord(
                uid="u1",
                decision="forward",
                reason="important cue: ntu",
                delete_after=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            )
            save_state(path, MailState(records={"u1": record}))

            state = load_state(path)

        self.assertEqual(state.records["u1"].decision, "forward")
        self.assertEqual(state.records["u1"].reason, "important cue: ntu")

    def test_ignores_unknown_record_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "records": {
                            "u1": {
                                "decision": "forward",
                                "future_field": "new value",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            state = load_state(path)

        self.assertEqual(state.records["u1"].uid, "u1")
        self.assertEqual(state.records["u1"].decision, "forward")


if __name__ == "__main__":
    unittest.main()
