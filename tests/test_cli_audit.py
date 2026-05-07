from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ntu_mail_forward.cli import audit_forward, cleanup_expired
from ntu_mail_forward.state import MailRecord, MailState, load_state


class FakePOP3:
    def __init__(self, messages: dict[int, EmailMessage]) -> None:
        self.messages = messages
        self.deleted: list[int] = []

    def retr(self, number: int) -> tuple[bytes, list[bytes], int]:
        data = self.messages[number].as_bytes()
        return b"+OK", data.splitlines(), len(data)

    def dele(self, number: int) -> tuple[bytes, list[bytes], int]:
        self.deleted.append(number)
        return b"+OK", [], 0


class FakeSMTP:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.quit_called = False

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def quit(self) -> None:
        self.quit_called = True


def make_message(sender: str, subject: str, body: str = "") -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = subject
    message.set_content(body)
    return message


class AuditForwardIntegrationTest(unittest.TestCase):
    def test_audit_forward_sends_only_forward_messages_and_never_deletes(self) -> None:
        pop3 = FakePOP3(
            {
                1: make_message("postmaster@ntu.edu.tw", "Account verification"),
                2: make_message("Rakuten <emails@emails.rakuten.com>", "15% Cash Back"),
            }
        )
        pop3.messages[2]["List-Unsubscribe"] = "<mailto:unsubscribe@example.com>"
        uid_map = {1: "uid-forward", 2: "uid-junk"}
        smtp = FakeSMTP()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "ntu_mail_forward.cli.connect_smtp", return_value=smtp
        ), patch.dict(
            os.environ,
            {"NTU_MAIL_USER": "b92901058", "NTU_FORWARD_TO": "gmail@example.com"},
            clear=True,
        ):
            state_file = Path(tmp) / "state.json"
            audit_csv = Path(tmp) / "audit.csv"
            with redirect_stdout(StringIO()):
                code = audit_forward(
                    pop3,
                    uid_map,
                    MailState(records={}),
                    state_file,
                    audit_csv,
                    limit=None,
                    retention_days=30,
                )
            state = load_state(state_file)
            audit_csv_exists = audit_csv.exists()

        self.assertEqual(code, 0)
        self.assertEqual(len(smtp.sent), 1)
        self.assertEqual(pop3.deleted, [])
        self.assertEqual(state.records["uid-forward"].decision, "forward")
        self.assertEqual(state.records["uid-junk"].decision, "junk")
        self.assertTrue(state.records["uid-forward"].delete_after)
        self.assertTrue(audit_csv_exists)

    def test_audit_forward_skips_processed_messages(self) -> None:
        pop3 = FakePOP3({1: make_message("postmaster@ntu.edu.tw", "Account notice")})
        smtp = FakeSMTP()
        state = MailState(records={"uid1": MailRecord(uid="uid1", decision="forward")})

        with tempfile.TemporaryDirectory() as tmp, patch(
            "ntu_mail_forward.cli.connect_smtp", return_value=smtp
        ):
            with redirect_stdout(StringIO()):
                code = audit_forward(
                    pop3,
                    {1: "uid1"},
                    state,
                    Path(tmp) / "state.json",
                    Path(tmp) / "audit.csv",
                    limit=None,
                    retention_days=30,
                )

        self.assertEqual(code, 0)
        self.assertEqual(smtp.sent, [])
        self.assertEqual(pop3.deleted, [])

    def test_cleanup_expired_deletes_only_expired_and_skips_missing_uidls(self) -> None:
        now = datetime.now(timezone.utc)
        expired = (now - timedelta(days=1)).isoformat()
        future = (now + timedelta(days=1)).isoformat()
        state = MailState(
            records={
                "expired": MailRecord(uid="expired", decision="forward", delete_after=expired),
                "future": MailRecord(uid="future", decision="junk", delete_after=future),
                "missing": MailRecord(uid="missing", decision="junk", delete_after=expired),
            }
        )
        pop3 = FakePOP3({})

        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            audit_csv = Path(tmp) / "audit.csv"
            with redirect_stdout(StringIO()):
                code = cleanup_expired(
                    pop3, {3: "expired", 4: "future"}, state, state_file, audit_csv
                )
            saved = load_state(state_file)

        self.assertEqual(code, 0)
        self.assertEqual(pop3.deleted, [3])
        self.assertTrue(saved.records["expired"].deleted_at)
        self.assertFalse(saved.records["future"].deleted_at)
        self.assertTrue(saved.records["missing"].deleted_at)


if __name__ == "__main__":
    unittest.main()
