from __future__ import annotations

import os
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ntu_mail_forward.cli import audit_forward, cleanup_expired, run
from ntu_mail_forward.classifier import Classifier, load_rules
from ntu_mail_forward.state import MailRecord, MailState, load_state


class FakePOP3:
    def __init__(self, messages: dict[int, EmailMessage]) -> None:
        self.messages = messages
        self.deleted: list[int] = []

    def retr(self, number: int) -> tuple[bytes, list[bytes], int]:
        data = self.messages[number].as_bytes()
        return b"+OK", data.splitlines(), len(data)

    def top(self, number: int, _lines: int) -> tuple[bytes, list[bytes], int]:
        data = self.messages[number].as_bytes()
        return b"+OK", data.splitlines(), len(data)

    def dele(self, number: int) -> tuple[bytes, list[bytes], int]:
        self.deleted.append(number)
        return b"+OK", [], 0

    def quit(self) -> None:
        pass


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
                classifier=Classifier(load_rules()),
            )
            state = load_state(state_file)
            audit_csv_exists = audit_csv.exists()
            audit_rows = audit_csv.read_text(encoding="utf-8").splitlines()

        self.assertEqual(code, 0)
        self.assertEqual(len(smtp.sent), 1)
        self.assertEqual(pop3.deleted, [])
        self.assertEqual(state.records["uid-forward"].decision, "forward")
        self.assertEqual(state.records["uid-junk"].decision, "junk")
        self.assertTrue(state.records["uid-forward"].delete_after)
        self.assertTrue(audit_csv_exists)
        self.assertEqual(len(audit_rows), 3)

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
                    classifier=Classifier(load_rules()),
                )

        self.assertEqual(code, 0)
        self.assertEqual(smtp.sent, [])
        self.assertEqual(pop3.deleted, [])

    def test_audit_forward_retains_duplicate_forward_with_new_uid(self) -> None:
        original_date = "Fri, 03 Jul 2026 12:02:28 +0000"
        duplicate = make_message(
            "Giloo 紀實影音 <edm@giloo.ist>",
            "深夜病房裡，所有狀況同時發生",
        )
        duplicate["Date"] = original_date
        pop3 = FakePOP3({2: duplicate})
        smtp = FakeSMTP()
        state = MailState(
            records={
                "old-uid": MailRecord(
                    uid="old-uid",
                    sender="Giloo 紀實影音 <edm@giloo.ist>",
                    subject="深夜病房裡，所有狀況同時發生",
                    date=original_date,
                    decision="forward",
                    forwarded_at="2026-07-03T12:05:00+00:00",
                )
            }
        )

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
                    {2: "new-uid"},
                    state,
                    state_file,
                    audit_csv,
                    limit=None,
                    retention_days=30,
                    classifier=Classifier(load_rules()),
                )
            saved = load_state(state_file)

        self.assertEqual(code, 0)
        self.assertEqual(smtp.sent, [])
        self.assertEqual(saved.records["new-uid"].decision, "junk")
        self.assertEqual(
            saved.records["new-uid"].reason,
            "duplicate of previously forwarded message",
        )

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

    def test_dry_run_does_not_load_classifier_rules(self) -> None:
        fake_pop3 = FakePOP3({1: make_message("sender@example.com", "hello")})
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.yaml"
            settings_file.write_text(
                "\n".join(
                    [
                        "accounts:",
                        "  - name: primary",
                        "    mail_user: user1",
                        "    mail_password: secret",
                        "    forward_to: one@example.com",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = Namespace(
                init=False,
                forward=False,
                audit_forward=False,
                cleanup_expired=False,
                dry_run=True,
                limit=1,
                retention_days=30,
                classifier_rules=Path("missing-rules.json"),
            )

            with patch("ntu_mail_forward.cli.DEFAULT_SETTINGS_FILE", settings_file), patch(
                "ntu_mail_forward.cli.parse_args", return_value=args
            ), patch(
                "ntu_mail_forward.cli.connect_pop3", return_value=fake_pop3
            ), patch(
                "ntu_mail_forward.cli.fetch_uid_map", return_value={1: "uid1"}
            ), patch(
                "ntu_mail_forward.cli.load_state", return_value=MailState(records={})
            ), redirect_stdout(StringIO()):
                code = run()

        self.assertEqual(code, 0)

    def test_settings_file_audit_forward_processes_isolated_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            global_rules = tmp_path / "global-rules.json"
            secondary_rules = tmp_path / "secondary-rules.json"
            global_rules.write_text(
                json.dumps({"always_junk_senders": ["sender1@example.com"]}),
                encoding="utf-8",
            )
            secondary_rules.write_text(
                json.dumps({"always_forward_senders": ["sender2@example.com"]}),
                encoding="utf-8",
            )
            settings_file = tmp_path / "settings.yaml"
            settings_file.write_text(
                "\n".join(
                    [
                        "accounts:",
                        "  - name: primary",
                        "    mail_user: user1",
                        "    mail_password: secret1",
                        "    forward_to: one@example.com",
                        "    state_file: primary-state.json",
                        "    audit_csv: primary-audit.csv",
                        "  - name: secondary",
                        "    mail_user: user2",
                        "    mail_password: secret2",
                        "    forward_to: two@example.com",
                        "    classifier_rules: secondary-rules.json",
                        "    state_file: secondary-state.json",
                        "    audit_csv: secondary-audit.csv",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = Namespace(
                init=False,
                forward=False,
                audit_forward=True,
                cleanup_expired=False,
                dry_run=False,
                limit=None,
                retention_days=30,
                classifier_rules=global_rules,
            )
            pop3_by_account = {
                "primary": FakePOP3({1: make_message("sender1@example.com", "Primary")}),
                "secondary": FakePOP3({1: make_message("sender2@example.com", "Secondary")}),
            }
            uid_maps = {
                id(pop3_by_account["primary"]): {1: "primary-uid"},
                id(pop3_by_account["secondary"]): {1: "secondary-uid"},
            }
            smtp_by_account = {"primary": FakeSMTP(), "secondary": FakeSMTP()}

            with patch("ntu_mail_forward.cli.DEFAULT_SETTINGS_FILE", settings_file), patch(
                "ntu_mail_forward.cli.parse_args", return_value=args
            ), patch(
                "ntu_mail_forward.cli.connect_pop3",
                side_effect=lambda account=None: pop3_by_account[account.name],
            ), patch(
                "ntu_mail_forward.cli.fetch_uid_map",
                side_effect=lambda pop3: uid_maps[id(pop3)],
            ), patch(
                "ntu_mail_forward.cli.connect_smtp",
                side_effect=lambda account=None: smtp_by_account[account.name],
            ), redirect_stdout(StringIO()):
                code = run()

            primary_state = load_state(tmp_path / "primary-state.json")
            secondary_state = load_state(tmp_path / "secondary-state.json")
            primary_audit_exists = (tmp_path / "primary-audit.csv").exists()
            secondary_audit_exists = (tmp_path / "secondary-audit.csv").exists()

        self.assertEqual(code, 0)
        self.assertEqual(primary_state.records["primary-uid"].decision, "junk")
        self.assertEqual(secondary_state.records["secondary-uid"].decision, "forward")
        self.assertEqual(smtp_by_account["primary"].sent, [])
        self.assertEqual(smtp_by_account["secondary"].sent[0]["To"], "two@example.com")
        self.assertTrue(primary_audit_exists)
        self.assertTrue(secondary_audit_exists)

    def test_settings_file_continues_after_account_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings_file = tmp_path / "settings.yaml"
            settings_file.write_text(
                "\n".join(
                    [
                        "accounts:",
                        "  - name: broken",
                        "    mail_user: bad",
                        "    mail_password: secret",
                        "    forward_to: bad@example.com",
                        "    state_file: broken-state.json",
                        "    audit_csv: broken-audit.csv",
                        "  - name: working",
                        "    mail_user: good",
                        "    mail_password: secret",
                        "    forward_to: good@example.com",
                        "    state_file: working-state.json",
                        "    audit_csv: working-audit.csv",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = Namespace(
                init=True,
                forward=False,
                audit_forward=False,
                cleanup_expired=False,
                dry_run=False,
                limit=None,
                retention_days=30,
                classifier_rules=Path("unused-rules.json"),
            )
            working_pop3 = FakePOP3({})

            def connect(account=None):
                if account.name == "broken":
                    raise OSError("login failed")
                return working_pop3

            with patch("ntu_mail_forward.cli.DEFAULT_SETTINGS_FILE", settings_file), patch(
                "ntu_mail_forward.cli.parse_args", return_value=args
            ), patch(
                "ntu_mail_forward.cli.connect_pop3", side_effect=connect
            ), patch(
                "ntu_mail_forward.cli.fetch_uid_map", return_value={1: "working-uid"}
            ), redirect_stdout(StringIO()):
                code = run()

            working_state = load_state(tmp_path / "working-state.json")

        self.assertEqual(code, 1)
        self.assertIn("working-uid", working_state.records)


if __name__ == "__main__":
    unittest.main()
