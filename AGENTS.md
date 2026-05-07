# Agent Guidance

## Project Overview

This repository contains a small Python utility that audits an NTU POP3 mailbox,
forwards important or uncertain messages to Gmail through NTU SMTP, records the
processing decision, and only deletes retained originals after their retention
window expires.

The code is intentionally dependency-light and currently uses the Python
standard library only. There is no package manager metadata yet, so run commands
from the repository root and invoke modules directly with `python3 -m ...`.

## Repository Layout

- `ntu_mail_forward/cli.py` is the command-line entry point and coordinates the
  modes: `--dry-run`, `--init`, `--audit-forward`, and `--cleanup-expired`.
- `ntu_mail_forward/mailbox.py` handles POP3/SMTP connections, UIDL fetching,
  message retrieval, and construction of forwarded messages.
- `ntu_mail_forward/classifier.py` classifies messages as `forward`, `junk`, or
  `error` using rule data.
- `ntu_mail_forward/state.py` reads and writes the local JSON state file.
- `classifier_rules.json` is the default classifier rules file. Keep changes
  focused and add/update classifier tests when changing rule behavior.
- `tests/` contains stdlib `unittest` tests plus `tests/probe_pop3_smtp.py` for
  optional live credential checks.
- `launchd/*.example.plist` are public macOS LaunchAgent templates. Real
  machine-specific plists without `.example` are intentionally ignored.

## Local Files and Secrets

- `.env.local` contains real account settings and must stay untracked. Do not
  print or copy its secret values into logs, commits, issues, or PR text.
- `.local/` contains runtime state, logs, and audit CSV output. Treat it as
  local-only operational data, not source.
- The default state file is `.local/pop3-state.json`; the default audit CSV is
  `.local/audit.csv`.
- The app uses POP3 UIDLs as stable message identities. Preserve that model when
  modifying processing or cleanup logic.

## Runtime Behavior

- Prefer `--audit-forward` for normal processing. It forwards messages classified
  as important or uncertain, records all processed messages, and retains POP3
  originals until the configured retention date.
- `--forward` is intentionally disabled because immediate-delete forwarding is
  unsafe.
- `--cleanup-expired` is the only mode that should delete POP3 messages, and it
  should delete only messages whose recorded `delete_after` has passed.
- POP3 deletes commit when `quit()` is called. Be careful with exception paths
  and tests around cleanup.
- The classifier should bias toward forwarding uncertain messages to avoid false
  negatives.

## Development Commands

- Preview mailbox headers without state changes:
  `python3 -m ntu_mail_forward.cli --dry-run`
- Mark current mailbox contents as already processed:
  `python3 -m ntu_mail_forward.cli --init`
- Audit and forward unprocessed mail:
  `python3 -m ntu_mail_forward.cli --audit-forward`
- Run cleanup:
  `python3 -m ntu_mail_forward.cli --cleanup-expired`
- Run the local test suite:
  `python3 -m unittest discover -s tests`
- Probe live POP3 credentials:
  `python3 tests/probe_pop3_smtp.py`
- Probe live SMTP credentials too:
  `NTU_TEST_SMTP=1 python3 tests/probe_pop3_smtp.py`

## Testing Guidance

- Use stdlib `unittest`; do not introduce a new test framework unless the
  project adds one deliberately.
- For mailbox behavior, prefer fake POP3/SMTP objects and environment patching
  as existing tests do. Avoid live network calls in normal tests.
- When changing forwarding message construction, cover body preservation,
  headers, sender defaults, and attachment behavior.
- When changing retention or state migration logic, cover both current state and
  legacy `seen_uids` payloads.
- When changing classifier rules, add focused examples in
  `tests/test_classifier.py` so the intended preference is documented.

## GitHub Operations

For any `gh` command or GitHub CLI operation, set `GH_HOST=github.com` so the command uses GitHub instead of falling back to `git.musta.ch`. If a command can infer the host from context or supports explicit targeting, also pass `--hostname github.com` or `-R github.com/OWNER/REPO`.

Configure GitHub CLI to use SSH for Git operations against GitHub:

```bash
GH_HOST=github.com gh config set git_protocol ssh --host github.com
```

When creating PRs, target the GitHub repository explicitly:

```bash
GH_HOST=github.com gh pr create \
  --repo aaronlin/ntu-mail-forward \
  --base main \
  --head <branch> \
  --draft
```

SSH handles Git transport for push/fetch operations, but `gh pr create` still uses the GitHub API to create the pull request. If PR creation fails with an auth error, refresh the GitHub CLI auth session with `GH_HOST=github.com gh auth login -h github.com`.
