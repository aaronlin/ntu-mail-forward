from __future__ import annotations

import argparse
import socket
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from .config import DEFAULT_SETTINGS_FILE, load_error_notifications, load_settings_file
from .mailbox import _default_sender, connect_smtp


MAX_OUTPUT_CHARS = 6000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send launchd failure notifications.")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--stdout-file", type=Path)
    parser.add_argument("--stderr-file", type=Path)
    parser.add_argument("--cwd", default="")
    parser.add_argument("--settings-file", type=Path, default=DEFAULT_SETTINGS_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sent = send_error_notification(
        job_name=args.job_name,
        command=args.command,
        exit_code=args.exit_code,
        stdout_text=_read_tail(args.stdout_file),
        stderr_text=_read_tail(args.stderr_file),
        cwd=args.cwd,
        settings_file=args.settings_file,
    )
    if sent:
        print(f"Sent error notification for {args.job_name}.")
    else:
        print("No error notification recipient configured.")


def send_error_notification(
    *,
    job_name: str,
    command: str,
    exit_code: int,
    stdout_text: str = "",
    stderr_text: str = "",
    cwd: str = "",
    settings_file: Path = DEFAULT_SETTINGS_FILE,
) -> bool:
    notification = load_error_notifications(settings_file)
    if notification is None:
        return False

    account = load_settings_file(settings_file)[0]
    message = build_error_message(
        recipient=notification.to,
        sender=account.forward_from or _default_sender(account.mail_user),
        job_name=job_name,
        command=command,
        exit_code=exit_code,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        cwd=cwd,
    )

    smtp = connect_smtp(account)
    try:
        smtp.send_message(message)
    finally:
        smtp.quit()
    return True


def build_error_message(
    *,
    recipient: str,
    sender: str,
    job_name: str,
    command: str,
    exit_code: int,
    stdout_text: str = "",
    stderr_text: str = "",
    cwd: str = "",
) -> EmailMessage:
    timestamp = datetime.now(timezone.utc).isoformat()
    host = socket.gethostname()
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"[ntu-mail-forward] {job_name} failed with exit code {exit_code}"
    message.set_content(
        "\n".join(
            [
                "An ntu-mail-forward launchd job failed.",
                "",
                f"Job: {job_name}",
                f"Exit code: {exit_code}",
                f"Timestamp: {timestamp}",
                f"Host: {host}",
                f"Working directory: {cwd or '(unknown)'}",
                f"Command: {command}",
                "",
                "STDERR tail:",
                stderr_text or "(empty)",
                "",
                "STDOUT tail:",
                stdout_text or "(empty)",
                "",
            ]
        )
    )
    return message


def _read_tail(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[-MAX_OUTPUT_CHARS:]


if __name__ == "__main__":
    main()
