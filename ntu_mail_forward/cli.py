from __future__ import annotations

import argparse
import poplib
import smtplib
import sys
from pathlib import Path

from .config import DEFAULT_ENV_FILE, DEFAULT_STATE_FILE, load_env_file
from .mailbox import (
    build_forward,
    connect_pop3,
    connect_smtp,
    describe_message,
    fetch_headers,
    fetch_message,
    fetch_uid_map,
)
from .state import load_seen_uids, save_seen_uids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Forward unseen POP3 messages, then delete forwarded originals."
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument(
        "--init",
        action="store_true",
        help="Mark current mailbox messages as seen without forwarding or deleting.",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="Forward unseen messages, then delete them from POP3.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print unseen message headers without forwarding, deleting, or changing state.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of unseen messages to process. Defaults to 2 for --dry-run and all for --forward.",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    load_env_file(args.env_file)

    if args.forward and args.dry_run:
        raise SystemExit("Use only one of --forward or --dry-run.")

    seen_uids = load_seen_uids(args.state_file)
    pop3 = connect_pop3()
    try:
        uid_map = fetch_uid_map(pop3)
        current_uids = set(uid_map.values())

        if args.init:
            save_seen_uids(args.state_file, current_uids)
            print(f"Initialized state with {len(current_uids)} existing message(s).")
            return 0

        unseen_items = [
            (number, uid)
            for number, uid in sorted(uid_map.items())
            if uid not in seen_uids
        ]

        limit = args.limit
        if limit is None and args.dry_run:
            limit = 2
        if limit is not None:
            unseen_items = unseen_items[-limit:]

        if not unseen_items:
            print("No unseen mail.")
            save_seen_uids(args.state_file, seen_uids | current_uids)
            return 0

        print(f"Found {len(unseen_items)} unseen message(s):")
        for number, uid in unseen_items:
            header = fetch_headers(pop3, number)
            print(f"- {describe_message(number, uid, header)}")

        if args.dry_run:
            print("Dry run only; no messages forwarded, deleted, or marked seen.")
            return 0

        if not args.forward:
            print("No action taken. Use --forward to forward and delete, or --dry-run to preview.")
            return 0

        smtp = connect_smtp()
        forwarded_uids: set[str] = set()
        try:
            for number, uid in unseen_items:
                original = fetch_message(pop3, number)
                smtp.send_message(build_forward(original))
                pop3.dele(number)
                forwarded_uids.add(uid)
                print(f"Forwarded and queued delete: {describe_message(number, uid, original)}")
        finally:
            smtp.quit()

        save_seen_uids(args.state_file, seen_uids | forwarded_uids)
        print(f"Forwarded {len(forwarded_uids)} message(s). POP3 deletes commit on QUIT.")
    finally:
        pop3.quit()

    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except (poplib.error_proto, smtplib.SMTPException) as exc:
        print(f"Mail protocol error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except OSError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
