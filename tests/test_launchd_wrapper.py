from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ntu_mail_forward.config import APP_ROOT


@unittest.skipUnless(shutil.which("zsh"), "The LaunchAgent wrapper requires zsh")
class LaunchAgentWrapperTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve() / "repo with spaces & symbols"
        (self.root / "launchd").mkdir(parents=True)
        self.wrapper = self.root / "launchd/run_with_error_email.sh"
        shutil.copy(APP_ROOT / "launchd/run_with_error_email.sh", self.wrapper)
        self.stdout_log = self.root / "logs/output.log"
        self.stderr_log = self.root / "logs/error.log"
        self.notification = self.root / "notification.json"
        self.interpreter = self.root / "fake-python"
        self.interpreter.write_text(
            f"#!{sys.executable}\n" + '''import json
import os
import sys
from pathlib import Path

if sys.argv[1:3] == ["-m", "ntu_mail_forward.notify_error"]:
    args = dict(zip(sys.argv[3::2], sys.argv[4::2]))
    Path(os.environ["NOTIFICATION_RECORD"]).write_text(json.dumps({
        "args": args,
        "cwd": os.getcwd(),
        "stdout": Path(args["--stdout-file"]).read_text(),
        "stderr": Path(args["--stderr-file"]).read_text(),
    }))
    print("synthetic notification result")
    sys.exit(int(os.environ["NOTIFY_EXIT"]))
print("synthetic command output")
print("synthetic command error", file=sys.stderr)
sys.exit(int(os.environ["COMMAND_EXIT"]))
'''
        )
        self.interpreter.chmod(0o755)

    def run_wrapper(self, command_exit=0, notify_exit=0):
        return subprocess.run(
            ["zsh", str(self.wrapper), "synthetic-job", str(self.stdout_log),
             str(self.stderr_log), str(self.interpreter), "--work"],
            cwd=self.root.parent,
            env={**os.environ, "COMMAND_EXIT": str(command_exit),
                 "NOTIFY_EXIT": str(notify_exit),
                 "NOTIFICATION_RECORD": str(self.notification)},
            capture_output=True, text=True, timeout=10,
        )

    def test_success_appends_logs_without_notification(self):
        self.stdout_log.parent.mkdir()
        self.stdout_log.write_text("previous output\n")
        self.stderr_log.write_text("previous error\n")
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stdout_log.read_text(), "previous output\nsynthetic command output\n")
        self.assertEqual(self.stderr_log.read_text(), "previous error\nsynthetic command error\n")
        self.assertFalse(self.notification.exists())

    def test_command_failure_notifies_with_output_and_repository_cwd(self):
        result = self.run_wrapper(command_exit=7)
        self.assertEqual(result.returncode, 7, result.stderr)
        notification = json.loads(self.notification.read_text())
        self.assertEqual(notification["cwd"], str(self.root))
        self.assertEqual(notification["args"]["--cwd"], str(self.root))
        self.assertEqual(notification["args"]["--job-name"], "synthetic-job")
        self.assertEqual(notification["args"]["--exit-code"], "7")
        self.assertEqual(notification["stdout"], "synthetic command output\n")
        self.assertEqual(notification["stderr"], "synthetic command error\n")
        self.assertIn("synthetic notification result", self.stderr_log.read_text())
        for option in ("--stdout-file", "--stderr-file"):
            self.assertFalse(Path(notification["args"][option]).exists())

    def test_notification_failure_preserves_command_exit_code(self):
        result = self.run_wrapper(command_exit=7, notify_exit=9)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertTrue(self.notification.exists())
        self.assertIn("Error notification failed with exit code 9.", self.stderr_log.read_text())


if __name__ == "__main__":
    unittest.main()
