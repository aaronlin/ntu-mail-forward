from __future__ import annotations

import poplib
import smtplib
import ssl
from collections.abc import Iterable
from email import message_from_bytes
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.policy import default

from .config import AccountConfig


def connect_pop3(account: AccountConfig) -> poplib.POP3_SSL:
    context = ssl.create_default_context()
    pop3 = poplib.POP3_SSL(
        account.pop3_host, account.pop3_port, context=context, timeout=30
    )
    try:
        pop3.user(account.mail_user)
        pop3.pass_(account.mail_password)
    except Exception:
        pop3.quit()
        raise
    return pop3


def connect_smtp(account: AccountConfig) -> smtplib.SMTP_SSL:
    context = ssl.create_default_context()
    smtp = smtplib.SMTP_SSL(
        account.smtp_host, account.smtp_port, context=context, timeout=30
    )
    try:
        smtp.login(account.mail_user, account.mail_password)
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


def build_forward(original: EmailMessage, account: AccountConfig) -> EmailMessage:
    original_subject = str(original.get("Subject", "(no subject)"))
    forwarded = EmailMessage()
    forwarded["From"] = account.forward_from or _default_sender(account.mail_user)
    forwarded["To"] = account.forward_to
    forwarded["Subject"] = f"Fwd: {original_subject}"
    forwarded.set_content(_forwarded_plain_text(original, original_subject))

    html_body = _message_body(original, "html")
    if html_body:
        forwarded.add_alternative(
            _forwarded_html(original, original_subject, html_body),
            subtype="html",
        )

    for attachment in _iter_original_attachments(original):
        forwarded.add_attachment(
            attachment.get_payload(decode=True) or b"",
            maintype=attachment.get_content_maintype(),
            subtype=attachment.get_content_subtype(),
            filename=attachment.get_filename(),
        )
    return forwarded


def _default_sender(username: str) -> str:
    if "@" in username:
        return username
    return f"{username}@ntu.edu.tw"


def _forwarded_plain_text(original: EmailMessage, original_subject: str) -> str:
    plain_body = _message_body(original, "plain")
    if plain_body is None:
        plain_body = "[Original message has no inline text body.]"

    return "\n".join(
        [
            "---------- Forwarded message ---------",
            f"From: {original.get('From', '')}",
            f"To: {original.get('To', '')}",
            f"Date: {original.get('Date', '')}",
            f"Subject: {original_subject}",
            "",
            plain_body,
        ]
    )


def _forwarded_html(
    original: EmailMessage, original_subject: str, html_body: str
) -> str:
    header = "<br>".join(
        [
            "---------- Forwarded message ---------",
            f"<b>From:</b> {_html_escape(str(original.get('From', '')))}",
            f"<b>To:</b> {_html_escape(str(original.get('To', '')))}",
            f"<b>Date:</b> {_html_escape(str(original.get('Date', '')))}",
            f"<b>Subject:</b> {_html_escape(original_subject)}",
        ]
    )
    return f"<div>{header}</div><br>{html_body}"


def _message_body(message: EmailMessage, subtype: str) -> str | None:
    body = message.get_body(preferencelist=(subtype,))
    if body is None:
        return None
    content = body.get_content()
    return str(content)


def _iter_original_attachments(message: EmailMessage) -> Iterable[EmailMessage]:
    for part in message.iter_attachments():
        if part.get_content_type() != "message/rfc822":
            yield part


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
