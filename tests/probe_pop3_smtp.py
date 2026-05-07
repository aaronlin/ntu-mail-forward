#!/usr/bin/env python3
"""Read-only POP3 probe and optional SMTP login probe."""

from __future__ import annotations

import poplib
import smtplib
import sys
from email.parser import BytesHeaderParser
from email.policy import default
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ntu_mail_forward.config import DEFAULT_SETTINGS_FILE, load_settings_file, optional_env
from ntu_mail_forward.mailbox import connect_pop3, connect_smtp


def print_recent_headers(pop3: poplib.POP3_SSL, sample_count: int) -> None:
    count, total_bytes = pop3.stat()
    print(f"POP3 mailbox: {count} messages, {total_bytes} bytes")
    if count == 0:
        return

    parser = BytesHeaderParser(policy=default)
    start = max(count - sample_count + 1, 1)
    print(f"\nMost recent {min(sample_count, count)} message headers:")
    for message_number in range(start, count + 1):
        _response, lines, _octets = pop3.top(message_number, 0)
        msg = parser.parsebytes(b"\n".join(lines))
        print(
            "- "
            f"{msg.get('Date', '')} | "
            f"{msg.get('From', '')} | "
            f"{msg.get('Subject', '')} | "
            f"{msg.get('Message-ID', '')}"
        )


def main() -> int:
    account = load_settings_file(DEFAULT_SETTINGS_FILE)[0]
    sample_count = int(optional_env("NTU_POP3_SAMPLE_COUNT") or "5")

    pop3 = connect_pop3(account)
    try:
        print(f"POP3 login succeeded for account {account.name}.")
        print_recent_headers(pop3, sample_count)
    finally:
        pop3.quit()

    if optional_env("NTU_TEST_SMTP") == "1":
        smtp = connect_smtp(account)
        try:
            print("\nSMTP login succeeded.")
        finally:
            smtp.quit()
    else:
        print("\nSkipped SMTP login test. Set NTU_TEST_SMTP=1 to enable it.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (poplib.error_proto, smtplib.SMTPException) as exc:
        print(f"Mail protocol error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except OSError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        raise SystemExit(3)
