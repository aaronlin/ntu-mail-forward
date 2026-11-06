from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ntu_mail_forward import launchd_setup
from ntu_mail_forward.config import APP_ROOT


class LaunchAgentSetupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "another @user & checkout"
        (self.root / "launchd").mkdir(parents=True)
        for template in (APP_ROOT / "launchd").glob("*.example.plist"):
            shutil.copy(template, self.root / "launchd" / template.name)
        self.python = self.root / ".venv/bin/python"
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        self.home = Path(directory.name) / "home"
        self.destination = self.home / "Library/LaunchAgents"

    def run_installer(self, *arguments):
        with patch.object(launchd_setup, "APP_ROOT", self.root), patch.object(
            Path, "home", return_value=self.home
        ), patch("sys.argv", ["launchd_setup", *arguments]), patch(
            "sys.platform", "darwin"
        ), redirect_stdout(StringIO()):
            launchd_setup.main()

    def test_renders_both_jobs_for_checkout_with_spaces_and_xml_characters(self):
        agents = launchd_setup.render_agents(self.root)
        self.assertEqual(len(agents), 2)
        modes = set()
        for path, payload in agents:
            parsed = plistlib.loads(plistlib.dumps(payload))
            self.assertEqual(parsed["WorkingDirectory"], str(self.root))
            self.assertEqual(parsed["ProgramArguments"][4], str(self.python))
            self.assertEqual(
                parsed["ProgramArguments"][0],
                str(self.root / "launchd/run_with_error_email.sh"),
            )
            self.assertNotIn("@REPO_ROOT@", str(parsed))
            self.assertNotIn("@PYTHON@", str(parsed))
            self.assertNotIn(".example", path.name)
            self.assertTrue(parsed["RunAtLoad"])
            modes.add(parsed["ProgramArguments"][-1])
            expected_interval = 86400 if parsed["Label"].endswith("cleanup") else 1800
            self.assertEqual(parsed["StartInterval"], expected_interval)
        self.assertEqual(modes, {"--audit-forward", "--cleanup-expired"})

    def test_missing_uv_environment_has_actionable_error(self):
        self.python.unlink()
        with self.assertRaisesRegex(SystemExit, "uv sync --locked"):
            launchd_setup.render_agents(self.root)

    def test_render_only_writes_valid_plists_without_registering(self):
        with patch.object(launchd_setup.subprocess, "run") as command:
            self.run_installer("--render-only")
        command.assert_not_called()
        self.assertFalse(self.destination.exists())
        for path, expected in launchd_setup.render_agents(self.root):
            self.assertEqual(plistlib.loads(path.read_bytes()), expected)

    def test_conflicting_file_or_symlink_is_preserved_before_unloading(self):
        self.destination.mkdir(parents=True)
        path, _ = launchd_setup.render_agents(self.root)[0]
        conflict = self.destination / path.name
        for kind in ("file", "symlink"):
            with self.subTest(kind=kind):
                if kind == "file":
                    conflict.write_text("unrelated job")
                else:
                    conflict.symlink_to(self.home / "unrelated.plist")
                with patch.object(launchd_setup.subprocess, "run") as command:
                    with self.assertRaisesRegex(SystemExit, "unrelated LaunchAgent"):
                        self.run_installer()
                command.assert_not_called()
                if kind == "file":
                    self.assertEqual(conflict.read_text(), "unrelated job")
                else:
                    self.assertEqual(conflict.readlink(), self.home / "unrelated.plist")
                conflict.unlink()

    def test_repeated_install_keeps_symlinks_and_reloads_loaded_jobs(self):
        loaded = set()
        events = []
        domain = f"gui/{os.getuid()}"

        def launchctl(arguments, **kwargs):
            operation, target = arguments[1:3]
            events.append(arguments)
            if operation == "print":
                code = 0 if target == domain or target in loaded else 1
                return subprocess.CompletedProcess(arguments, code)
            if operation == "bootout":
                loaded.remove(target)
            elif operation == "bootstrap":
                link = Path(arguments[3])
                self.assertTrue(link.is_symlink())
                payload = plistlib.loads(link.read_bytes())
                service = f"{domain}/{payload['Label']}"
                self.assertNotIn(service, loaded)
                loaded.add(service)
            return subprocess.CompletedProcess(arguments, 0)

        with patch.object(launchd_setup.subprocess, "run", side_effect=launchctl):
            self.run_installer()
            first_links = {path.name: path.lstat().st_ino for path in self.destination.iterdir()}
            self.run_installer()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(sum(event[1] == "bootout" for event in events), 2)
        self.assertEqual(sum(event[1] == "bootstrap" for event in events), 4)
        for path, _ in launchd_setup.render_agents(self.root):
            link = self.destination / path.name
            self.assertEqual(link.readlink(), path)
            self.assertEqual(link.lstat().st_ino, first_links[link.name])


if __name__ == "__main__":
    unittest.main()
