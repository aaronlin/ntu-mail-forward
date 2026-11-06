from __future__ import annotations

import unittest
from dataclasses import replace
from email.message import EmailMessage

from ntu_mail_forward.config import AccountConfig
from ntu_mail_forward.mailbox import _default_sender, build_forward


class DefaultSenderTest(unittest.TestCase):
    def test_uses_existing_email_address(self) -> None:
        self.assertEqual(_default_sender("user@example.com"), "user@example.com")

    def test_expands_bare_ntu_username(self) -> None:
        self.assertEqual(_default_sender("b92901058"), "b92901058@ntu.edu.tw")


class BuildForwardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.account = AccountConfig(
            name="synthetic", mail_user="student", mail_password="synthetic",
            forward_to="gmail@example.com",
        )

    def test_inlines_original_body_without_eml_attachment(self) -> None:
        original = EmailMessage()
        original["From"] = "sender@example.com"
        original["To"] = "recipient@example.com"
        original["Date"] = "Thu, 07 May 2026 08:16:10 +0000"
        original["Subject"] = "Original subject"
        original.set_content("Hello from the original body.")

        forwarded = build_forward(original, self.account)

        self.assertEqual(forwarded["From"], "student@ntu.edu.tw")
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

        forwarded = build_forward(original, self.account)

        attachments = list(forwarded.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "report.pdf")
        self.assertEqual(attachments[0].get_payload(decode=True), b"report-data")

    def test_preserves_html_and_uses_configured_sender(self) -> None:
        original = EmailMessage()
        original["Subject"] = "Report <ready>"
        original["From"] = "Sender <sender@example.com>"
        original.set_content("Plain report.")
        original.add_alternative("<p>HTML report.</p>", subtype="html")
        account = replace(self.account, forward_from="custom@example.com")

        forwarded = build_forward(original, account)

        self.assertEqual(forwarded["From"], "custom@example.com")
        self.assertEqual(forwarded["To"], "gmail@example.com")
        self.assertIn("Plain report.", forwarded.get_body(preferencelist=("plain",)).get_content())
        html = forwarded.get_body(preferencelist=("html",)).get_content()
        self.assertIn("<p>HTML report.</p>", html)
        self.assertIn("Report &lt;ready&gt;", html)
        self.assertIn("Sender &lt;sender@example.com&gt;", html)


if __name__ == "__main__":
    unittest.main()
