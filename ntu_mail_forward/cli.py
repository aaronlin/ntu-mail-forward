from __future__ import annotations

import argparse
import csv
import poplib
import smtplib
import sys
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import StringIO
from pathlib import Path

from .classifier import DEFAULT_RULES_FILE, ERROR, FORWARD, JUNK, Classifier, load_rules
from .config import (
    AccountConfig,
    DEFAULT_SETTINGS_FILE,
    load_settings_file,
)
from .mailbox import (
    build_forward,
    connect_pop3,
    connect_smtp,
    describe_message,
    fetch_headers,
    fetch_message,
    fetch_uid_map,
)
from .state import (
    MailRecord,
    load_state,
    save_seen_uids,
    save_state,
    utc_now,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit NTU POP3 mail, forward important messages, and clean up after retention."
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Mark current mailbox messages as seen without forwarding or deleting.",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="Deprecated unsafe mode. Use --audit-forward instead.",
    )
    parser.add_argument(
        "--audit-forward",
        action="store_true",
        help="Classify unprocessed messages, forward important/uncertain mail, and retain all originals.",
    )
    parser.add_argument(
        "--cleanup-expired",
        action="store_true",
        help="Delete POP3 messages whose recorded retention period has expired.",
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
        help="Maximum number of unseen messages to process. Defaults to 2 for --dry-run and all for --audit-forward.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Days to retain processed originals before --cleanup-expired may delete them.",
    )
    parser.add_argument(
        "--classifier-rules",
        type=Path,
        default=DEFAULT_RULES_FILE,
        help="JSON classifier rules file.",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    selected_modes = [
        args.init,
        args.forward,
        args.audit_forward,
        args.cleanup_expired,
        args.dry_run,
    ]
    if sum(bool(mode) for mode in selected_modes) > 1:
        raise SystemExit("Use only one action at a time.")
    if args.forward:
        raise SystemExit("Immediate-delete --forward is disabled. Use --audit-forward.")
    if args.retention_days < 0:
        raise SystemExit("--retention-days must be 0 or greater.")

    return run_accounts(args)


def run_accounts(args: argparse.Namespace) -> int:
    accounts = load_settings_file(DEFAULT_SETTINGS_FILE)
    failures = 0

    for account in accounts:
        buffer = StringIO()
        code = 1
        print(f"[{account.name}] Starting")
        try:
            with redirect_stdout(buffer):
                code = run_single_account(args, account)
        except Exception as exc:
            print(f"[{account.name}] Error: {exc}")
            failures += 1
        else:
            if code != 0:
                failures += 1
        finally:
            for line in buffer.getvalue().splitlines():
                print(f"[{account.name}] {line}")
            print(f"[{account.name}] Finished with exit code {code}")

    if failures:
        print(f"Combined run complete: {failures} account(s) failed.")
        return 1

    print(f"Combined run complete: {len(accounts)} account(s) succeeded.")
    return 0


def run_single_account(args: argparse.Namespace, account: AccountConfig) -> int:
    state_file = account.state_file
    audit_csv = account.audit_csv
    if state_file is None or audit_csv is None:
        raise SystemExit("Missing state or audit path.")

    state = load_state(state_file)
    pop3 = connect_pop3(account)
    try:
        uid_map = fetch_uid_map(pop3)
        current_uids = set(uid_map.values())

        if args.init:
            save_seen_uids(state_file, current_uids)
            print(f"Initialized state with {len(current_uids)} existing message(s).")
            return 0

        if args.cleanup_expired:
            return cleanup_expired(pop3, uid_map, state, state_file, audit_csv)

        if args.audit_forward:
            rules_file = (
                account.classifier_rules
                if account.classifier_rules is not None
                else args.classifier_rules
            )
            classifier = Classifier(load_rules(rules_file))
            return audit_forward(
                pop3,
                uid_map,
                state,
                state_file,
                audit_csv,
                args.limit,
                args.retention_days,
                classifier,
                account,
            )

        unseen_items = [
            (number, uid)
            for number, uid in sorted(uid_map.items())
            if uid not in state.records
        ]

        limit = args.limit
        if limit is None and args.dry_run:
            limit = 2
        if limit is not None:
            unseen_items = unseen_items[-limit:]

        if not unseen_items:
            print("No unseen mail.")
            return 0

        print(f"Found {len(unseen_items)} unseen message(s):")
        for number, uid in unseen_items:
            header = fetch_headers(pop3, number)
            print(f"- {describe_message(number, uid, header)}")

        if args.dry_run:
            print("Dry run only; no messages forwarded, deleted, or marked seen.")
            return 0

        print("No action taken. Use --audit-forward to classify and forward, or --dry-run to preview.")
    finally:
        pop3.quit()

    return 0


def audit_forward(
    pop3: poplib.POP3_SSL,
    uid_map: dict[int, str],
    state,
    state_file: Path,
    audit_csv: Path,
    limit: int | None,
    retention_days: int,
    classifier: Classifier | None = None,
    account: AccountConfig | None = None,
) -> int:
    items = [
        (number, uid)
        for number, uid in sorted(uid_map.items())
        if uid not in state.records
    ]
    skipped = len(uid_map) - len(items)
    if limit is not None:
        items = items[-limit:]

    if not items:
        print(f"No unprocessed mail. Skipped {skipped} already processed message(s).")
        return 0

    classifier = classifier or Classifier()
    smtp = None
    rows: list[MailRecord] = []
    counts: Counter[str] = Counter(skipped=skipped)
    try:
        for number, uid in items:
            now = utc_now()
            delete_after = (
                datetime.now(timezone.utc) + timedelta(days=retention_days)
            ).isoformat()
            try:
                original = fetch_message(pop3, number)
                classification = classifier.classify(original)
                record = _record_from_message(
                    uid,
                    number,
                    original,
                    classification.decision,
                    classification.reason,
                    now,
                    delete_after,
                )
                if classification.decision == FORWARD:
                    if smtp is None:
                        smtp = connect_smtp(account)
                    smtp.send_message(build_forward(original, account))
                    record.forwarded_at = utc_now()
                    print(f"Forwarded: {describe_message(number, uid, original)}")
                elif classification.decision == JUNK:
                    print(f"Junk retained: {describe_message(number, uid, original)}")
                else:
                    record.decision = ERROR
                    record.error = f"Unexpected decision: {classification.decision}"
                    print(f"Error: {describe_message(number, uid, original)} | {record.error}")
            except Exception as exc:
                record = MailRecord(
                    uid=uid,
                    message_number=number,
                    decision=ERROR,
                    reason="processing error",
                    processed_at=now,
                    error=str(exc),
                )
                print(f"Error processing #{number} ({uid}): {exc}")

            state.records[uid] = record
            rows.append(record)
            counts[record.decision] += 1
            save_state(state_file, state)
            append_audit_csv(audit_csv, [record])
    finally:
        if smtp is not None:
            smtp.quit()

    print(
        "Audit-forward summary: "
        f"forwarded={counts[FORWARD]}, junk={counts[JUNK]}, "
        f"errors={counts[ERROR]}, skipped={counts['skipped']}"
    )
    print(f"Audit CSV: {audit_csv}")
    return 0 if counts[ERROR] == 0 else 1


def cleanup_expired(
    pop3: poplib.POP3_SSL,
    uid_map: dict[int, str],
    state,
    state_file: Path,
    audit_csv: Path,
) -> int:
    uid_to_number = {uid: number for number, uid in uid_map.items()}
    now = datetime.now(timezone.utc)
    rows: list[MailRecord] = []
    counts: Counter[str] = Counter()

    for uid, record in sorted(state.records.items()):
        if record.deleted_at or not record.delete_after:
            continue
        delete_after = _parse_datetime(record.delete_after)
        if delete_after is None or delete_after > now:
            continue
        number = uid_to_number.get(uid)
        if number is None:
            record.deleted_at = utc_now()
            record.error = "UID not present during cleanup; treated as already gone"
            counts["missing"] += 1
            rows.append(record)
            continue
        pop3.dele(number)
        record.deleted_at = utc_now()
        record.message_number = number
        counts["deleted"] += 1
        rows.append(record)
        print(f"Deleted expired POP3 message #{number} ({uid})")

    save_state(state_file, state)
    if rows:
        append_audit_csv(audit_csv, rows)
    print(
        "Cleanup summary: "
        f"deleted={counts['deleted']}, missing={counts['missing']}, "
        f"retained={len(state.records) - counts['deleted'] - counts['missing']}"
    )
    print("POP3 deletes commit on QUIT.")
    return 0


def _record_from_message(
    uid: str,
    number: int,
    message: EmailMessage,
    decision: str,
    reason: str,
    processed_at: str,
    delete_after: str,
) -> MailRecord:
    return MailRecord(
        uid=uid,
        message_number=number,
        sender=str(message.get("From", "")),
        subject=str(message.get("Subject", "")),
        date=str(message.get("Date", "")),
        decision=decision,
        reason=reason,
        processed_at=processed_at,
        delete_after=delete_after,
    )


def append_audit_csv(path: Path, rows: list[MailRecord]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fieldnames = [
        "uid",
        "message_number",
        "sender",
        "subject",
        "date",
        "decision",
        "reason",
        "processed_at",
        "forwarded_at",
        "delete_after",
        "deleted_at",
        "error",
    ]
    with path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for record in rows:
            writer.writerow({name: getattr(record, name) for name in fieldnames})


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
