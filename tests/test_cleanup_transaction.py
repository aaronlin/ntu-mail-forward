from __future__ import annotations

import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ntu_mail_forward.cli import run_single_account
from ntu_mail_forward.config import AccountConfig
from ntu_mail_forward.state import MailRecord, MailState, load_state, save_state


class TransactionPOP3:
    def __init__(self, mailbox, *, quit_failure="", fail_delete=None):
        self.mailbox = mailbox
        self.pending = set()
        self.quit_failure = quit_failure
        self.fail_delete = fail_delete
        self.quit_count = 0

    def uidl(self):
        return b"+OK", [f"{number} {uid}".encode() for number, uid in self.mailbox.items()], 0

    def dele(self, number):
        if number == self.fail_delete:
            raise OSError("synthetic DELE failure")
        self.pending.add(number)
        return b"+OK"

    def quit(self):
        self.quit_count += 1
        if self.quit_failure == "before":
            raise OSError("synthetic QUIT failure before commit")
        for number in self.pending:
            self.mailbox.pop(number, None)
        self.pending.clear()
        if self.quit_failure == "after":
            raise OSError("synthetic QUIT failure after commit")

    def close(self):
        self.pending.clear()


class CleanupTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.account = AccountConfig(
            name="synthetic", mail_user="synthetic", mail_password="synthetic",
            forward_to="synthetic@example.invalid",
            state_file=root / "state.json", audit_csv=root / "audit.csv",
        )
        records = {
            uid: MailRecord(uid=uid, decision="junk", delete_after=date)
            for uid, date in (
                ("expired-a", "2000-01-01T00:00:00+00:00"),
                ("expired-b", "2000-01-01T00:00:00+00:00"),
                ("future", "2999-01-01T00:00:00+00:00"),
                ("invalid", "invalid"),
                ("initialized", ""),
            )
        }
        save_state(self.account.state_file, MailState(records=records))
        self.mailbox = {index: uid for index, uid in enumerate(records, start=1)}

    def run_cleanup(self, session):
        args = Namespace(init=False, cleanup_expired=True)
        with patch("ntu_mail_forward.cli.connect_pop3", return_value=session), redirect_stdout(StringIO()):
            return run_single_account(args, self.account)

    def assert_pending_state(self):
        state = load_state(self.account.state_file)
        self.assertFalse(state.records["expired-a"].deleted_at)
        self.assertFalse(state.records["expired-b"].deleted_at)
        self.assertFalse(self.account.audit_csv.exists())

    def test_success_commits_once_and_preserves_unexpired_or_invalid_records(self):
        session = TransactionPOP3(self.mailbox)
        self.assertEqual(self.run_cleanup(session), 0)
        self.assertEqual(session.quit_count, 1)
        self.assertEqual(set(self.mailbox.values()), {"future", "invalid", "initialized"})
        state = load_state(self.account.state_file)
        self.assertTrue(state.records["expired-a"].deleted_at)
        self.assertTrue(state.records["expired-b"].deleted_at)
        for uid in ("future", "invalid", "initialized"):
            self.assertFalse(state.records[uid].deleted_at)
        self.assertEqual(self.account.audit_csv.read_text().count("expired-a"), 1)
        self.assertEqual(self.run_cleanup(TransactionPOP3(self.mailbox)), 0)
        self.assertEqual(self.account.audit_csv.read_text().count("expired-a"), 1)

    def test_quit_failure_before_commit_preserves_state_and_retry_deletes(self):
        with self.assertRaisesRegex(OSError, "QUIT failure"):
            self.run_cleanup(TransactionPOP3(self.mailbox, quit_failure="before"))
        self.assert_pending_state()
        self.assertIn("expired-a", self.mailbox.values())
        self.assertEqual(self.run_cleanup(TransactionPOP3(self.mailbox)), 0)
        self.assertNotIn("expired-a", self.mailbox.values())
        self.assertTrue(load_state(self.account.state_file).records["expired-a"].deleted_at)

    def test_quit_failure_after_commit_reconciles_missing_uid_on_retry(self):
        with self.assertRaisesRegex(OSError, "QUIT failure"):
            self.run_cleanup(TransactionPOP3(self.mailbox, quit_failure="after"))
        self.assert_pending_state()
        self.assertNotIn("expired-a", self.mailbox.values())
        self.assertEqual(self.run_cleanup(TransactionPOP3(self.mailbox)), 0)
        record = load_state(self.account.state_file).records["expired-a"]
        self.assertTrue(record.deleted_at)
        self.assertIn("UID not present", record.error)

    def test_partial_delete_failure_does_not_commit_and_can_retry(self):
        with self.assertRaisesRegex(OSError, "DELE failure"):
            self.run_cleanup(TransactionPOP3(self.mailbox, fail_delete=2))
        self.assert_pending_state()
        self.assertIn("expired-a", self.mailbox.values())
        self.assertEqual(self.run_cleanup(TransactionPOP3(self.mailbox)), 0)
        self.assertNotIn("expired-a", self.mailbox.values())
        self.assertNotIn("expired-b", self.mailbox.values())

    def test_state_write_failure_after_commit_reconciles_on_retry(self):
        with patch("ntu_mail_forward.cli.save_state", side_effect=OSError("synthetic disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                self.run_cleanup(TransactionPOP3(self.mailbox))
        self.assert_pending_state()
        self.assertNotIn("expired-a", self.mailbox.values())
        self.assertEqual(self.run_cleanup(TransactionPOP3(self.mailbox)), 0)
        self.assertTrue(load_state(self.account.state_file).records["expired-a"].deleted_at)


if __name__ == "__main__":
    unittest.main()
