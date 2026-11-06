# NTU Mail Forwarder

Audit unseen NTU POP3 mail, forward important or uncertain messages to Gmail
through NTU SMTP, and retain originals for 30 days before cleanup can delete them.

## Setup

Install uv, then run these commands from the repository root. uv uses Python
3.12 from `.python-version` and installs the locked PyYAML dependency into `.venv`.

```sh
uv sync --locked
cp settings.yaml.example settings.yaml
chmod 600 settings.yaml
mkdir -p .local/logs
```

Edit `settings.yaml` with the local account values. The process stops at startup
if `settings.yaml` is missing or does not contain at least one valid account.

## Usage

Preview 1-2 unseen messages without forwarding or deleting:

```sh
uv run python -m ntu_mail_forward.cli --dry-run
```

Mark current mailbox contents as already seen without forwarding or deleting:

```sh
uv run python -m ntu_mail_forward.cli --init
```

Audit unseen mail, forward important or uncertain messages, and retain originals for
30 days before cleanup can delete them:

```sh
uv run python -m ntu_mail_forward.cli --audit-forward
```

Process a smaller batch first:

```sh
uv run python -m ntu_mail_forward.cli --audit-forward --limit 50
```

Delete only messages whose retention period has expired:

```sh
uv run python -m ntu_mail_forward.cli --cleanup-expired
```

Adjust retention:

```sh
uv run python -m ntu_mail_forward.cli --audit-forward --retention-days 30
```

Classifier rules are stored in `classifier_rules.json`. Tune the sender, subject,
and term lists there for another mailbox, or point at a different rules file:

```sh
uv run python -m ntu_mail_forward.cli --audit-forward --classifier-rules my-rules.json
```

## Account settings

`settings.yaml` is the default config for one or more NTU accounts. Each account
keeps separate POP3 state and audit history. The command continues after an
account failure, then exits nonzero if any account failed.

```yaml
accounts:
  - name: primary
    mail_user: student_id
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
uv run python tests/probe_pop3_smtp.py
NTU_TEST_SMTP=1 uv run python tests/probe_pop3_smtp.py
```

## macOS LaunchAgents

After setup, register both jobs for the current macOS user:

```sh
uv run python -m ntu_mail_forward.launchd_setup
```

The installer reads the two tracked templates in `launchd/`, resolves the current
repository and `.venv` paths, and writes gitignored local plists. It symlinks
those files into `~/Library/LaunchAgents/` and loads both jobs. Each job runs when
loaded. Rerun the installer after moving the repository or changing a template.

The jobs use `.venv/bin/python` directly, so launchd does not need uv on its PATH.
Both jobs read `settings.yaml` and process all configured accounts:

- `com.example.ntu-mail-forward.audit` runs `--audit-forward` every 30 minutes.
- `com.example.ntu-mail-forward.cleanup` runs `--cleanup-expired` every 24 hours.

To generate local plists without registering or running the jobs:

```sh
uv run python -m ntu_mail_forward.launchd_setup --render-only
```

Check each job's status after its run finishes:

```sh
launchctl print "gui/$(id -u)/com.example.ntu-mail-forward.audit"
launchctl print "gui/$(id -u)/com.example.ntu-mail-forward.cleanup"
```

A successful run has `last exit code = 0`. Logs are in `.local/logs/`.
The LaunchAgents call `launchd/run_with_error_email.sh`, which appends command
output to the logs and sends an email on failure if `error_notifications.to` is
configured.

## Run tests

```sh
uv run python -m unittest discover -s tests
```

GitHub Actions runs these tests on macOS with Python 3.12 for pull requests and
pushes to `main`. CI installs dependencies with `uv sync --locked`, checks the
shell wrapper and plist syntax, and validates generated LaunchAgents without
registering them. Mail connections and notifications use test doubles.

Cleanup records deletions only after POP3 confirms `QUIT`. If the connection
fails, the next cleanup checks UIDLs again before recording a deletion.
