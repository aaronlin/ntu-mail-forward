from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from email.message import EmailMessage

from ntu_mail_forward.classifier import (
    FORWARD,
    JUNK,
    Classifier,
    classify_message,
    load_rules,
)


def message(
    sender: str,
    subject: str,
    body: str = "",
    headers: dict[str, str] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = subject
    for key, value in (headers or {}).items():
        msg[key] = value
    msg.set_content(body)
    return msg


class ClassifierTest(unittest.TestCase):
    def test_ntu_admin_mail_forwards(self) -> None:
        result = classify_message(message("postmaster@ntu.edu.tw", "Account notice"))
        self.assertEqual(result.decision, FORWARD)

    def test_bank_statement_forwards(self) -> None:
        result = classify_message(message("bank@example.com", "Monthly statement"))
        self.assertEqual(result.decision, FORWARD)

    def test_receipt_travel_and_job_mail_forwards(self) -> None:
        samples = [
            message("store@example.com", "Your receipt"),
            message("airline@example.com", "Flight itinerary"),
            message("recruiter@example.com", "Interview schedule"),
        ]
        self.assertTrue(all(classify_message(msg).decision == FORWARD for msg in samples))

    def test_marketing_newsletter_is_junk(self) -> None:
        result = classify_message(
            message(
                "Rakuten <emails@emails.rakuten.com>",
                "15% Cash Back today only",
                headers={"List-Unsubscribe": "<mailto:unsubscribe@example.com>"},
            )
        )
        self.assertEqual(result.decision, JUNK)

    def test_ambiguous_mail_forwards_by_default(self) -> None:
        result = classify_message(message("friend@example.com", "Following up"))
        self.assertEqual(result.decision, FORWARD)

    def test_important_cue_overrides_list_unsubscribe(self) -> None:
        result = classify_message(
            message(
                "security@example.com",
                "Password reset verification",
                headers={"List-Unsubscribe": "<mailto:unsubscribe@example.com>"},
            )
        )
        self.assertEqual(result.decision, FORWARD)

    def test_initium_is_not_junk(self) -> None:
        result = classify_message(
            message("端周報 Initium Weekly <membership@theinitium.com>", "白宮槍響驚雲")
        )
        self.assertEqual(result.decision, FORWARD)

    def test_google_security_alert_is_ignored(self) -> None:
        result = classify_message(
            message("Google <no-reply@accounts.google.com>", "Security alert for vagante@gmail.com")
        )
        self.assertEqual(result.decision, JUNK)

    def test_ntu_spam_quarantine_notice_is_ignored(self) -> None:
        result = classify_message(
            message("NTU郵件過濾系統 <postmaster@ntu.edu.tw>", "垃圾信隔離通知 (Spam Quarantine Notification)")
        )
        self.assertEqual(result.decision, JUNK)

    def test_atcoder_is_ignored(self) -> None:
        result = classify_message(
            message("AtCoder System Mail <noreply@atcoder.jp>", "AtCoder Regular Contest 218 告知")
        )
        self.assertEqual(result.decision, JUNK)

    def test_marketing_body_terms_do_not_make_promo_important(self) -> None:
        result = classify_message(
            message(
                "UNIQLO TAIWAN <email@edm.uniqlo.tw>",
                "AIRism 搭一件，告別不舒適！***Marketing***",
                body="order class office account",
                headers={"List-Unsubscribe": "<mailto:unsubscribe@example.com>"},
            )
        )
        self.assertEqual(result.decision, JUNK)

    def test_reviewed_junk_senders_are_junk(self) -> None:
        samples = [
            message("HSBC Taiwan <onlineservices@informationservices.hsbc.com.tw>", "母親節限定優惠"),
            message("JR九州 <webmaster@mail.jrkyushu.co.jp>", "会員さま限定プラン"),
            message("Instapaper <no-reply@instapaper.com>", "Instapaper Weekly"),
        ]
        self.assertTrue(all(classify_message(msg).decision == JUNK for msg in samples))

    def test_turbotax_uses_content_to_classify(self) -> None:
        self.assertEqual(
            classify_message(
                message("TurboTax <TurboTax@em1.turbotax.intuit.com>", "LAST CHANCE: File by tonight to save")
            ).decision,
            FORWARD,
        )
        self.assertEqual(
            classify_message(
                message("TurboTax <TurboTax@em1.turbotax.intuit.com>", "Let an expert handle your taxes")
            ).decision,
            JUNK,
        )

    def test_invoice_lottery_notice_is_kept(self) -> None:
        result = classify_message(
            message("統一數位會員 via ThinkWave <noreply@thinkwave.com>", "7-ELEVEN 電子發票核對與中獎確認通知")
        )
        self.assertEqual(result.decision, FORWARD)

    def test_giloo_is_kept(self) -> None:
        result = classify_message(
            message("Giloo 紀實影音 <edm@giloo.ist>", "【新片上架】石黑一雄小說改編")
        )
        self.assertEqual(result.decision, FORWARD)

    def test_slack_notice_is_kept(self) -> None:
        result = classify_message(
            message(
                "Slack <no-reply@slack.com>",
                "Notice: Content older than one year will be deleted from your free workspace",
                body="marketing sale",
                headers={"List-Unsubscribe": "<mailto:unsubscribe@example.com>"},
            )
        )
        self.assertEqual(result.decision, FORWARD)

    def test_custom_rules_file_can_override_sender_preferences(self) -> None:
        with TemporaryDirectory() as tmp:
            rules_file = Path(tmp) / "rules.json"
            rules_file.write_text(
                """
{
  "important_header_terms": [],
  "junk_terms": [],
  "promo_senders": [],
  "always_forward_senders": ["custom-keep.example"],
  "always_forward_subjects": [],
  "always_junk_senders": ["custom-junk.example"],
  "ignore_patterns": [],
  "sender_content_rules": [],
  "bulk_headers": []
}
""".strip(),
                encoding="utf-8",
            )
            classifier = Classifier(load_rules(rules_file))
            self.assertEqual(
                classifier.classify(message("a@custom-keep.example", "hello")).decision,
                FORWARD,
            )
            self.assertEqual(
                classifier.classify(message("a@custom-junk.example", "hello")).decision,
                JUNK,
            )


if __name__ == "__main__":
    unittest.main()
