from __future__ import annotations

import os
import unittest
from email.message import EmailMessage
from unittest.mock import patch

from ntu_mail_forward.mailbox import _default_sender, build_forward


class DefaultSenderTest(unittest.TestCase):
    def test_uses_existing_email_address(self) -> None:
        self.assertEqual(_default_sender("user@example.com"), "user@example.com")

    def test_expands_bare_ntu_username(self) -> None:
        self.assertEqual(_default_sender("b92901058"), "b92901058@ntu.edu.tw")


class BuildForwardTest(unittest.TestCase):
    def test_inlines_original_body_without_eml_attachment(self) -> None:
        original = EmailMessage()
        original["From"] = "sender@example.com"
        original["To"] = "recipient@example.com"
        original["Date"] = "Thu, 07 May 2026 08:16:10 +0000"
        original["Subject"] = "Original subject"
        original.set_content("Hello from the original body.")

        env = {
            **os.environ,
            "NTU_MAIL_USER": "b92901058",
            "NTU_FORWARD_TO": "gmail@example.com",
        }
        with patch.dict(os.environ, env, clear=True):
            forwarded = build_forward(original)

        self.assertEqual(forwarded["From"], "b92901058@ntu.edu.tw")
        self.assertEqual(forwarded["To"], "gmail@example.com")
        self.assertEqual(forwarded["Subject"], "Fwd: Original subject")
        self.assertIn("Hello from the original body.", forwarded.get_content())
        self.assertEqual(list(forwarded.iter_attachments()), [])

    def test_copies_original_file_attachments(self) -> None:
        original = EmailMessage()
        original["Subject"] = "Report"
        original.set_content("See attached.")
        original.add_attachment(
            b"report-data",
            maintype="application",
            subtype="pdf",
            filename="report.pdf",
        )

        env = {
            **os.environ,
            "NTU_MAIL_USER": "b92901058",
            "NTU_FORWARD_TO": "gmail@example.com",
        }
        with patch.dict(os.environ, env, clear=True):
            forwarded = build_forward(original)

        attachments = list(forwarded.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "report.pdf")
        self.assertEqual(attachments[0].get_payload(decode=True), b"report-data")


if __name__ == "__main__":
    unittest.main()
