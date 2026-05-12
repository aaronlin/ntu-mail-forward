from __future__ import annotations

import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from ntu_mail_forward.notify_error import build_error_message, send_error_notification


class FakeSMTP:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.quit_called = False

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def quit(self) -> None:
        self.quit_called = True


def write_settings(path: Path, include_notification: bool) -> None:
    lines = []
    if include_notification:
        lines.extend(["error_notifications:", "  to: alerts@example.com", ""])
    lines.extend(
        [
            "accounts:",
            "  - name: primary",
            "    mail_user: user1",
            "    mail_password: secret",
            "    forward_to: one@example.com",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


class ErrorNotificationTest(unittest.TestCase):
    def test_build_error_message_includes_failure_context(self) -> None:
        message = build_error_message(
            recipient="alerts@example.com",
            sender="user1@ntu.edu.tw",
            job_name="audit",
            command="python3 -m ntu_mail_forward.cli --audit-forward",
            exit_code=1,
            stdout_text="normal output",
            stderr_text="bad output",
            cwd="/repo",
        )

        body = message.get_content()
        self.assertEqual(message["To"], "alerts@example.com")
        self.assertEqual(message["From"], "user1@ntu.edu.tw")
        self.assertIn("audit failed with exit code 1", message["Subject"])
        self.assertIn("Command: python3 -m ntu_mail_forward.cli --audit-forward", body)
        self.assertIn("STDERR tail:\nbad output", body)
        self.assertIn("STDOUT tail:\nnormal output", body)

    def test_send_error_notification_uses_first_account_smtp(self) -> None:
        smtp = FakeSMTP()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "ntu_mail_forward.notify_error.connect_smtp", return_value=smtp
        ) as connect:
            settings_file = Path(tmp) / "settings.yaml"
            write_settings(settings_file, include_notification=True)

            sent = send_error_notification(
                job_name="cleanup",
                command="python3 -m ntu_mail_forward.cli --cleanup-expired",
                exit_code=1,
                stderr_text="cleanup failed",
                settings_file=settings_file,
            )

        self.assertTrue(sent)
        connect.assert_called_once()
        self.assertEqual(len(smtp.sent), 1)
        self.assertEqual(smtp.sent[0]["To"], "alerts@example.com")
        self.assertIn("cleanup failed", smtp.sent[0].get_content())
        self.assertTrue(smtp.quit_called)

    def test_send_error_notification_is_noop_without_recipient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "ntu_mail_forward.notify_error.connect_smtp"
        ) as connect:
            settings_file = Path(tmp) / "settings.yaml"
            write_settings(settings_file, include_notification=False)

            sent = send_error_notification(
                job_name="audit",
                command="python3 -m ntu_mail_forward.cli --audit-forward",
                exit_code=1,
                settings_file=settings_file,
            )

        self.assertFalse(sent)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
