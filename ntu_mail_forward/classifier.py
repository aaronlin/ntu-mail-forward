from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage


FORWARD = "forward"
JUNK = "junk"
ERROR = "error"


@dataclass(frozen=True)
class Classification:
    decision: str
    reason: str


IMPORTANT_TERMS = (
    "ntu",
    "national taiwan university",
    "台大",
    "臺大",
    "professor",
    "department",
    "admin",
    "academic",
    "seminar",
    "conference",
    "bank",
    "statement",
    "invoice",
    "receipt",
    "payment",
    "transaction",
    "security",
    "verification",
    "verify",
    "password",
    "security alert",
    "action needed",
    "government",
    "immigration",
    "flight",
    "itinerary",
    "interview",
    "application",
    "cfp:",
    "shipment",
    "delivery",
)

JUNK_TERMS = (
    "marketing",
    "newsletter",
    "unsubscribe",
    "cash back",
    "coupon",
    "discount",
    "sale",
    "promo",
    "promotion",
    "limited time",
    "last chance",
    "deal",
    "deals",
    "reward",
    "points",
    "shopping",
    "cart",
    "retail",
    "旅遊優惠",
    "優惠",
    "折扣",
    "回饋",
    "購物",
)

PROMO_SENDERS = (
    "rakuten",
    "shopback",
    "uniqlo",
    "gu taiwan",
    "pinkoi",
    "booking.com",
    "yelp",
    "packt",
    "lomography",
    "zeczec",
    "nova",
    "nanit",
    "garmin",
    "gopro",
    "cole haan",
    "ikea",
    "watsons",
    "trip.com",
    "accupass",
    "maxmypoint",
    "synology",
    "quantopian",
    "hihibox",
    "hsbc taiwan",
    "jr九州",
    "jrkyushu",
    "instapaper",
)

ALWAYS_FORWARD_SENDERS = (
    "initium.com",
    "theinitium.com",
    "giloo",
)

ALWAYS_FORWARD_SUBJECTS = (
    "電子發票核對與中獎確認通知",
)

ALWAYS_JUNK_SENDERS = (
    "hsbc taiwan",
    "jr九州",
    "jrkyushu",
    "instapaper",
)

IGNORE_PATTERNS = (
    ("accounts.google.com", "security alert"),
    ("postmaster@ntu.edu.tw", "垃圾信隔離通知"),
    ("postmaster@ntu.edu.tw", "spam quarantine notification"),
    ("atcoder.jp", ""),
)

BULK_HEADERS = (
    "list-unsubscribe",
    "list-id",
    "precedence",
    "x-campaign",
    "x-mailgun",
    "x-mc",
)


def classify_message(message: EmailMessage) -> Classification:
    sender = _header(message, "From")
    subject = _header(message, "Subject")
    body = _body_text(message)
    sender_text = sender.lower()
    subject_text = subject.lower()
    header_text = " ".join([sender, subject]).lower()
    searchable = " ".join([sender, subject, body]).lower()

    ignore_reason = _ignore_reason(sender_text, subject_text)
    if ignore_reason:
        return Classification(JUNK, ignore_reason)

    turbotax_reason = _turbotax_reason(sender_text, subject_text, searchable)
    if turbotax_reason:
        decision = FORWARD if turbotax_reason.startswith("important") else JUNK
        return Classification(decision, turbotax_reason)

    always_junk_matches = _matches(sender_text, ALWAYS_JUNK_SENDERS)
    if always_junk_matches:
        return Classification(
            JUNK,
            f"review preference: {', '.join(always_junk_matches[:2])}",
        )

    always_forward_matches = _matches(sender_text, ALWAYS_FORWARD_SENDERS)
    if always_forward_matches:
        return Classification(
            FORWARD,
            f"review preference: {', '.join(always_forward_matches[:2])}",
        )

    always_forward_subject_matches = _matches(subject_text, ALWAYS_FORWARD_SUBJECTS)
    if always_forward_subject_matches:
        return Classification(
            FORWARD,
            f"review preference: {', '.join(always_forward_subject_matches[:2])}",
        )

    important_matches = _matches(header_text, IMPORTANT_TERMS)
    if important_matches:
        return Classification(
            FORWARD,
            f"important cue: {', '.join(important_matches[:3])}",
        )

    junk_matches = _matches(searchable, JUNK_TERMS)
    bulk_matches = _bulk_matches(message)
    promo_matches = _matches(sender.lower(), PROMO_SENDERS)
    if junk_matches and (bulk_matches or promo_matches):
        reasons = junk_matches[:2] + bulk_matches[:2] + promo_matches[:1]
        return Classification(JUNK, f"high-confidence junk: {', '.join(reasons)}")

    return Classification(FORWARD, "uncertain; forwarding to avoid false negative")


def _ignore_reason(sender: str, subject: str) -> str:
    for sender_pattern, subject_pattern in IGNORE_PATTERNS:
        if sender_pattern not in sender:
            continue
        if subject_pattern and subject_pattern not in subject:
            continue
        if "google" in sender_pattern:
            return "review preference: already delivered to Gmail"
        if "postmaster@ntu.edu.tw" in sender_pattern:
            return "review preference: ignore NTU spam quarantine notice"
        if "atcoder" in sender_pattern:
            return "review preference: ignore AtCoder"
    return ""


def _turbotax_reason(sender: str, subject: str, searchable: str) -> str:
    if "turbotax" not in sender:
        return ""
    junk_terms = (
        "expert",
        "cash back",
        "save ",
        "savings",
        "discount",
        "offer",
        "deal",
        "bigger tax savings",
    )
    important_terms = (
        "last chance",
        "deadline",
        "due",
        "file by",
        "final notice",
        "important notice",
        "account needs to be activated",
        "avoid extra charges",
    )
    if _matches(subject, important_terms):
        return "important cue: TurboTax reminder"
    if _matches(searchable, junk_terms):
        return "review preference: TurboTax promotional content"
    return "uncertain TurboTax; forwarding to avoid false negative"


def _header(message: EmailMessage, name: str) -> str:
    return str(message.get(name, ""))


def _matches(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _bulk_matches(message: EmailMessage) -> list[str]:
    matches: list[str] = []
    for name in BULK_HEADERS:
        value = str(message.get(name, ""))
        if value:
            matches.append(name)
        if name == "precedence" and value.lower() in {"bulk", "list", "junk"}:
            matches.append(f"precedence:{value.lower()}")
    return matches


def _body_text(message: EmailMessage) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.is_attachment():
                continue
            if part.get_content_maintype() == "text":
                parts.append(_part_content(part))
    elif message.get_content_maintype() == "text":
        parts.append(_part_content(message))
    return " ".join(parts)


def _part_content(part: EmailMessage) -> str:
    try:
        return str(part.get_content())
    except (LookupError, UnicodeDecodeError):
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
