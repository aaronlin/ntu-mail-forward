# NTU Mail Forwarder

Forward unseen NTU POP3 mail to Gmail through NTU SMTP, then delete successfully forwarded originals from the NTU POP3 mailbox.

## Setup

```sh
cp .env.local.example .env.local
chmod 600 .env.local
mkdir -p .local/logs
```

Edit `.env.local` with the local account values.

## Usage

Preview 1-2 unseen messages without forwarding or deleting:

```sh
python3 -m ntu_mail_forward.cli --dry-run
```

Mark current mailbox contents as already seen without forwarding or deleting:

```sh
python3 -m ntu_mail_forward.cli --init
```

Audit unseen mail, forward important or uncertain messages, and retain originals for
30 days before cleanup can delete them:

```sh
python3 -m ntu_mail_forward.cli --audit-forward
```

Process a smaller batch first:

```sh
python3 -m ntu_mail_forward.cli --audit-forward --limit 50
```

Delete only messages whose retention period has expired:

```sh
python3 -m ntu_mail_forward.cli --cleanup-expired
```

Adjust retention:

```sh
python3 -m ntu_mail_forward.cli --audit-forward --retention-days 30
```

Classifier rules are stored in `classifier_rules.json`. Tune the sender, subject,
and term lists there for another mailbox, or point at a different rules file:

```sh
python3 -m ntu_mail_forward.cli --audit-forward --classifier-rules my-rules.json
```

Test POP3 and optionally SMTP login:

```sh
python3 tests/probe_pop3_smtp.py
NTU_TEST_SMTP=1 python3 tests/probe_pop3_smtp.py
```

## macOS LaunchAgent

Use `launchd/com.personal-automation.ntu-mail-forward.example.plist` as the tracked public template.

Create a local real plist at `launchd/com.personal-automation.ntu-mail-forward.plist`. It is gitignored because it contains machine-specific paths. For this machine, the real plist assumes this repo lives at:

```text
~/git/personal/ntu-mail-forward
```

Install it:

```sh
mkdir -p ~/Library/LaunchAgents
cp launchd/com.personal-automation.ntu-mail-forward.plist ~/Library/LaunchAgents/
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.personal-automation.ntu-mail-forward.plist
```

Logs are written under `.local/logs/`.
