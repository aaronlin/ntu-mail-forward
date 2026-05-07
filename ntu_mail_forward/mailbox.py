from __future__ import annotations

import poplib
import smtplib
import ssl
from email import message_from_bytes
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.policy import default

from .config import env, optional_env


def connect_pop3() -> poplib.POP3_SSL:
    host = env("NTU_POP3_HOST", "msa.ntu.edu.tw")
    port = int(env("NTU_POP3_PORT", "995"))
    username = env("NTU_MAIL_USER")
    password = env("NTU_MAIL_PASSWORD")

    context = ssl.create_default_context()
    pop3 = poplib.POP3_SSL(host, port, context=context, timeout=30)
    try:
        pop3.user(username)
        pop3.pass_(password)
    except Exception:
        pop3.quit()
        raise
    return pop3


def connect_smtp() -> smtplib.SMTP_SSL:
    username = env("NTU_MAIL_USER")
    password = env("NTU_MAIL_PASSWORD")
    host = env("NTU_SMTP_HOST", "smtps.ntu.edu.tw")
    port = int(env("NTU_SMTP_PORT", "465"))

    context = ssl.create_default_context()
    smtp = smtplib.SMTP_SSL(host, port, context=context, timeout=30)
    try:
        smtp.login(username, password)
    except Exception:
        smtp.quit()
        raise
    return smtp


def fetch_uid_map(pop3: poplib.POP3_SSL) -> dict[int, str]:
    response, lines, _octets = pop3.uidl()
    if not response.startswith(b"+OK"):
        raise RuntimeError(f"UIDL failed: {response!r}")

    uid_map: dict[int, str] = {}
    for line in lines:
        number_text, uid = line.decode("utf-8", errors="replace").split(" ", 1)
        uid_map[int(number_text)] = uid
    return uid_map


def fetch_headers(pop3: poplib.POP3_SSL, message_number: int) -> EmailMessage:
    parser = BytesHeaderParser(policy=default)
    _response, lines, _octets = pop3.top(message_number, 0)
    return parser.parsebytes(b"\n".join(lines))


def fetch_message(pop3: poplib.POP3_SSL, message_number: int) -> EmailMessage:
    _response, lines, _octets = pop3.retr(message_number)
    return message_from_bytes(b"\r\n".join(lines), policy=default)


def describe_message(message_number: int, uid: str, msg: EmailMessage) -> str:
    subject = str(msg.get("Subject", "(no subject)"))
    sender = str(msg.get("From", "(unknown sender)"))
    date = str(msg.get("Date", "(unknown date)"))
    message_id = str(msg.get("Message-ID", uid))
    return f"#{message_number} | {date} | {sender} | {subject} | {message_id}"


def build_forward(original: EmailMessage) -> EmailMessage:
    username = env("NTU_MAIL_USER")
    recipient = optional_env("NTU_FORWARD_TO")
    sender = optional_env("NTU_FORWARD_FROM") or username
    if not recipient:
        raise SystemExit("Missing required environment variable: NTU_FORWARD_TO")

    original_subject = str(original.get("Subject", "(no subject)"))
    forwarded = EmailMessage()
    forwarded["From"] = sender
    forwarded["To"] = recipient
    forwarded["Subject"] = f"Fwd: {original_subject}"
    forwarded.set_content(
        "\n".join(
            [
                "Forwarded from POP3 mailbox.",
                "",
                f"Original From: {original.get('From', '')}",
                f"Original To: {original.get('To', '')}",
                f"Original Date: {original.get('Date', '')}",
                f"Original Subject: {original_subject}",
                "",
                "The original message is attached as message/rfc822.",
            ]
        )
    )
    forwarded.add_attachment(
        original,
        subtype="rfc822",
        filename="forwarded-message.eml",
    )
    return forwarded
