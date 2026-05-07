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

Forward unseen mail and delete successfully forwarded originals from NTU:

```sh
python3 -m ntu_mail_forward.cli --forward
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
