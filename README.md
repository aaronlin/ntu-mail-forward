# NTU Mail Forwarder

Forward unseen NTU POP3 mail to Gmail through NTU SMTP, then delete successfully forwarded originals from the NTU POP3 mailbox.

## Setup

```sh
cp settings.yaml.example settings.yaml
chmod 600 settings.yaml
mkdir -p .local/logs
```

Edit `settings.yaml` with the local account values. The process stops at startup
if `settings.yaml` is missing or does not contain at least one valid account.

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

## Account Settings

`settings.yaml` is the default config for one or more NTU accounts. Each account
keeps separate POP3 state and audit history. The command continues after an
account failure, then exits nonzero if any account failed.

```yaml
accounts:
  - name: primary
    mail_user: b92901058
    mail_password: ...
    forward_to: gmail@example.com
  - name: secondary
    mail_user: another_id
    mail_password: ...
    forward_to: other@example.com
    classifier_rules: classifier_rules_secondary.json
```

Optional per-account fields are `forward_from`, `pop3_host`, `pop3_port`,
`smtp_host`, `smtp_port`, `classifier_rules`, `state_file`, and `audit_csv`.
Relative paths are resolved from the settings file location. If `state_file` and
`audit_csv` are omitted, they default to:

```text
.local/accounts/<name>/pop3-state.json
.local/accounts/<name>/audit.csv
```

To email yourself when a scheduled LaunchAgent run exits with an error, add a
private notification recipient to your ignored local `settings.yaml`:

```yaml
error_notifications:
  to: alerts@example.com
```

Failure notifications are sent through the first configured account's NTU SMTP
settings.

Test POP3 and optionally SMTP login:

```sh
python3 tests/probe_pop3_smtp.py
NTU_TEST_SMTP=1 python3 tests/probe_pop3_smtp.py
```

## macOS LaunchAgent

Use these tracked public templates:

- `launchd/com.personal-automation.ntu-mail-forward.example.plist` for frequent audit/forward runs.
- `launchd/com.personal-automation.ntu-mail-forward-cleanup.example.plist` for daily expired-message cleanup.

For multiple accounts, use one audit job and one cleanup job. Both read the
default `settings.yaml`:

```text
/usr/bin/python3 -m ntu_mail_forward.cli --audit-forward
/usr/bin/python3 -m ntu_mail_forward.cli --cleanup-expired
```

Create local real plists under `launchd/` without the `.example` suffix. They are gitignored because they contain machine-specific paths. For this machine, the real plists assume this repo lives at:

```text
~/git/personal/ntu-mail-forward
```

Install it:

```sh
mkdir -p ~/Library/LaunchAgents
cp launchd/com.personal-automation.ntu-mail-forward.plist ~/Library/LaunchAgents/
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.personal-automation.ntu-mail-forward.plist
cp launchd/com.personal-automation.ntu-mail-forward-cleanup.plist ~/Library/LaunchAgents/
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.personal-automation.ntu-mail-forward-cleanup.plist
```

Logs are written under `.local/logs/`.

The LaunchAgents call `launchd/run_with_error_email.sh`, which preserves the
existing stdout/stderr logs and sends a notification email on any nonzero exit.
After changing loaded plist content, reload or kickstart the relevant
LaunchAgent so launchd picks up the new command.
