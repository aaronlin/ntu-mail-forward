from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ntu_mail_forward.config import load_settings_file


class SettingsFileTest(unittest.TestCase):
    def test_loads_accounts_and_derives_default_paths(self) -> None:
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

            accounts = load_settings_file(settings_file)

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, "primary")
        self.assertEqual(accounts[0].mail_user, "user1")
        self.assertEqual(accounts[0].forward_to, "one@example.com")
        self.assertTrue(str(accounts[0].state_file).endswith(".local/accounts/primary/pop3-state.json"))
        self.assertTrue(str(accounts[0].audit_csv).endswith(".local/accounts/primary/audit.csv"))

    def test_rejects_duplicate_names(self) -> None:
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
                        "  - name: primary",
                        "    mail_user: user2",
                        "    mail_password: secret",
                        "    forward_to: two@example.com",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                load_settings_file(settings_file)

    def test_rejects_missing_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.yaml"
            settings_file.write_text(
                "accounts:\n  - name: primary\n",
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                load_settings_file(settings_file)

    def test_resolves_explicit_paths_relative_to_accounts_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "config" / "settings.yaml"
            settings_file.parent.mkdir()
            settings_file.write_text(
                "\n".join(
                    [
                        "accounts:",
                        "  - name: secondary",
                        "    mail_user: user2",
                        "    mail_password: secret",
                        "    forward_to: two@example.com",
                        "    state_file: state.json",
                        "    audit_csv: audit.csv",
                        "    classifier_rules: rules.json",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            account = load_settings_file(settings_file)[0]

        self.assertEqual(account.state_file, settings_file.parent / "state.json")
        self.assertEqual(account.audit_csv, settings_file.parent / "audit.csv")
        self.assertEqual(account.classifier_rules, settings_file.parent / "rules.json")

    def test_rejects_empty_accounts_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.yaml"
            settings_file.write_text("accounts: []\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                load_settings_file(settings_file)

    def test_rejects_missing_settings_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                load_settings_file(Path(tmp) / "settings.yaml")


if __name__ == "__main__":
    unittest.main()
