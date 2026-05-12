#!/bin/zsh
set -u

if [ "$#" -lt 4 ]; then
  echo "usage: $0 JOB_NAME STDOUT_LOG STDERR_LOG COMMAND [ARG ...]" >&2
  exit 64
fi

job_name="$1"
stdout_log="$2"
stderr_log="$3"
shift 3

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
mkdir -p -- "$(dirname -- "$stdout_log")" "$(dirname -- "$stderr_log")"

stdout_tmp="$(mktemp "${TMPDIR:-/tmp}/ntu-mail-forward-out.XXXXXX")"
stderr_tmp="$(mktemp "${TMPDIR:-/tmp}/ntu-mail-forward-err.XXXXXX")"

(
  cd "$repo_root" || exit 1
  "$@"
) >"$stdout_tmp" 2>"$stderr_tmp"
command_status="$?"

cat "$stdout_tmp" >>"$stdout_log"
cat "$stderr_tmp" >>"$stderr_log"

if [ "$command_status" -ne 0 ]; then
  notify_tmp="$(mktemp "${TMPDIR:-/tmp}/ntu-mail-forward-notify.XXXXXX")"
  "$1" -m ntu_mail_forward.notify_error \
    --job-name "$job_name" \
    --command "$*" \
    --exit-code "$command_status" \
    --stdout-file "$stdout_tmp" \
    --stderr-file "$stderr_tmp" \
    --cwd "$repo_root" >"$notify_tmp" 2>&1
  notify_status="$?"
  cat "$notify_tmp" >>"$stderr_log"
  rm -f -- "$notify_tmp"
  if [ "$notify_status" -ne 0 ]; then
    echo "Error notification failed with exit code $notify_status." >>"$stderr_log"
  fi
fi

rm -f -- "$stdout_tmp" "$stderr_tmp"
exit "$command_status"
