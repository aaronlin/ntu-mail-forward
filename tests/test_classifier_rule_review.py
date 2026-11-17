from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ntu_mail_forward.classifier import Classifier, FORWARD, JUNK, load_rules
from review_classifier_rules import CASES_FILE, review_message


class ClassifierRuleReviewTest(unittest.TestCase):
    def test_review_cases(self) -> None:
        classifier = Classifier(load_rules())
        cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    classifier.classify(review_message(case)).decision,
                    case["after"],
                )

    def test_custom_group_modes(self) -> None:
        samples = [
            ({"all": ["promo"], "any": ["offer"]}, "promotion offered", JUNK),
            ({"all": ["promo"], "any": ["offer"], "match_mode": "substring"}, "promotion offered", JUNK),
            ({"all": ["promo"], "any": ["offer"], "match_mode": "words"}, "promotion offer", FORWARD),
            ({"all": ["promo"], "any": ["offer"], "match_mode": "words"}, "promo offered", FORWARD),
            ({"all": ["promo"], "any": ["offer"], "match_mode": "words"}, "[PROMO] offer", JUNK),
            ({"all": ["promo"], "match_mode": "words"}, "promo", JUNK),
            ({"any": ["offer"], "match_mode": "words"}, "offer", JUNK),
            ({"all": ["健康"], "match_mode": "words"}, "健康研究", JUNK),
            ({"all": ["cfp:"], "match_mode": "words"}, "XCFP: notes", JUNK),
        ]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            for group, subject, expected in samples:
                with self.subTest(group=group, subject=subject):
                    path.write_text(
                        json.dumps({"always_junk_subject_groups": [group]}),
                        encoding="utf-8",
                    )
                    classifier = Classifier(load_rules(path))
                    self.assertEqual(
                        classifier.classify(review_message({
                            "sender": "notice@example.com", "subject": subject,
                        })).decision,
                        expected,
                    )

    def test_unknown_group_mode_is_rejected_when_loading(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            for mode in ("word", "", None, 1, ["words"]):
                with self.subTest(mode=mode):
                    path.write_text(
                        json.dumps({"always_junk_subject_groups": [{
                            "all": ["cfp"], "match_mode": mode,
                        }]}),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        load_rules(path)

    def test_custom_marketing_modes(self) -> None:
        samples = [
            ({}, {"junk_terms": ["cart"]}, "notice@example.com", "Cartography notes", JUNK),
            ({"marketing_match_mode": "substring"}, {"junk_terms": ["cart"]}, "notice@example.com", "Cartography notes", JUNK),
            ({"marketing_match_mode": "words"}, {"junk_terms": ["cart"]}, "notice@example.com", "Cartography notes", FORWARD),
            ({}, {"promo_senders": ["nova"]}, "Innovation Lab <notice@example.com>", "Hello", JUNK),
            ({"marketing_match_mode": "words"}, {"promo_senders": ["nova"]}, "Innovation Lab <notice@example.com>", "Hello", FORWARD),
            ({"marketing_match_mode": "words"}, {"promo_senders": ["nova"]}, "NOVA <notice@example.com>", "Hello", JUNK),
            ({"marketing_match_mode": "words"}, {"always_junk_subjects": ["cart"]}, "notice@example.com", "Cartography notes", JUNK),
            ({"marketing_match_mode": "words"}, {"sender_content_rules": [{"sender": "tax", "junk_terms": ["promo"]}]}, "tax@example.com", "Promotion", JUNK),
        ]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            for mode, rules, sender, subject, expected in samples:
                with self.subTest(mode=mode, rules=rules, subject=subject):
                    path.write_text(
                        json.dumps({**rules, **mode, "bulk_headers": ["list-id"]}),
                        encoding="utf-8",
                    )
                    classifier = Classifier(load_rules(path))
                    self.assertEqual(
                        classifier.classify(review_message({
                            "sender": sender,
                            "subject": subject,
                            "headers": {"List-ID": "<community.example.com>"},
                        })).decision,
                        expected,
                    )

    def test_unknown_marketing_mode_is_rejected_when_loading(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            for mode in ("word", "", None, 1, ["words"]):
                with self.subTest(mode=mode):
                    path.write_text(
                        json.dumps({"marketing_match_mode": mode}),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        load_rules(path)


if __name__ == "__main__":
    unittest.main()
