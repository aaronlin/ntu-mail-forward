from __future__ import annotations

import json
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from .config import APP_ROOT


FORWARD = "forward"
JUNK = "junk"
ERROR = "error"
DEFAULT_RULES_FILE = APP_ROOT / "classifier_rules.json"


@dataclass(frozen=True)
class Classification:
    decision: str
    reason: str


@dataclass(frozen=True)
class SenderSubjectRule:
    sender: str
    subject: str = ""
    reason: str = ""


@dataclass(frozen=True)
class SenderContentRule:
    sender: str
    forward_subject_terms: tuple[str, ...] = ()
    junk_terms: tuple[str, ...] = ()
    forward_reason: str = "important cue"
    junk_reason: str = "review preference"
    uncertain_reason: str = "uncertain; forwarding to avoid false negative"


@dataclass(frozen=True)
class ClassifierRules:
    important_header_terms: tuple[str, ...] = ()
    junk_terms: tuple[str, ...] = ()
    promo_senders: tuple[str, ...] = ()
    always_forward_senders: tuple[str, ...] = ()
    always_forward_subjects: tuple[str, ...] = ()
    always_junk_senders: tuple[str, ...] = ()
    always_junk_subjects: tuple[str, ...] = ()
    ignore_patterns: tuple[SenderSubjectRule, ...] = ()
    sender_content_rules: tuple[SenderContentRule, ...] = ()
    bulk_headers: tuple[str, ...] = ()


@dataclass
class Classifier:
    rules: ClassifierRules = field(default_factory=lambda: load_rules())

    def classify(self, message: EmailMessage) -> Classification:
        sender = _header(message, "From")
        subject = _header(message, "Subject")
        body = _body_text(message)
        sender_text = sender.lower()
        subject_text = subject.lower()
        header_text = " ".join([sender, subject]).lower()
        searchable = " ".join([sender, subject, body]).lower()

        ignore_reason = self._ignore_reason(sender_text, subject_text)
        if ignore_reason:
            return Classification(JUNK, ignore_reason)

        content_rule_result = self._sender_content_result(
            sender_text, subject_text, searchable
        )
        if content_rule_result is not None:
            return content_rule_result

        always_junk_matches = _matches(sender_text, self.rules.always_junk_senders)
        if always_junk_matches:
            return Classification(
                JUNK,
                f"review preference: {', '.join(always_junk_matches[:2])}",
            )

        always_junk_subject_matches = _matches(
            subject_text, self.rules.always_junk_subjects
        )
        if always_junk_subject_matches:
            return Classification(
                JUNK,
                f"review preference: {', '.join(always_junk_subject_matches[:2])}",
            )

        always_forward_matches = _matches(sender_text, self.rules.always_forward_senders)
        if always_forward_matches:
            return Classification(
                FORWARD,
                f"review preference: {', '.join(always_forward_matches[:2])}",
            )

        always_forward_subject_matches = _matches(
            subject_text, self.rules.always_forward_subjects
        )
        if always_forward_subject_matches:
            return Classification(
                FORWARD,
                f"review preference: {', '.join(always_forward_subject_matches[:2])}",
            )

        important_matches = _matches(header_text, self.rules.important_header_terms)
        if important_matches:
            return Classification(
                FORWARD,
                f"important cue: {', '.join(important_matches[:3])}",
            )

        junk_matches = _matches(searchable, self.rules.junk_terms)
        bulk_matches = self._bulk_matches(message)
        promo_matches = _matches(sender.lower(), self.rules.promo_senders)
        if junk_matches and (bulk_matches or promo_matches):
            reasons = junk_matches[:2] + bulk_matches[:2] + promo_matches[:1]
            return Classification(JUNK, f"high-confidence junk: {', '.join(reasons)}")

        return Classification(FORWARD, "uncertain; forwarding to avoid false negative")

    def _ignore_reason(self, sender: str, subject: str) -> str:
        for rule in self.rules.ignore_patterns:
            if rule.sender not in sender:
                continue
            if rule.subject and rule.subject not in subject:
                continue
            return rule.reason or f"review preference: ignored {rule.sender}"
        return ""

    def _sender_content_result(
        self, sender: str, subject: str, searchable: str
    ) -> Classification | None:
        for rule in self.rules.sender_content_rules:
            if rule.sender not in sender:
                continue
            if _matches(subject, rule.forward_subject_terms):
                return Classification(FORWARD, rule.forward_reason)
            if _matches(searchable, rule.junk_terms):
                return Classification(JUNK, rule.junk_reason)
            return Classification(FORWARD, rule.uncertain_reason)
        return None

    def _bulk_matches(self, message: EmailMessage) -> list[str]:
        matches: list[str] = []
        for name in self.rules.bulk_headers:
            value = str(message.get(name, ""))
            if value:
                matches.append(name)
            if name == "precedence" and value.lower() in {"bulk", "list", "junk"}:
                matches.append(f"precedence:{value.lower()}")
        return matches


def classify_message(message: EmailMessage) -> Classification:
    return Classifier().classify(message)


def load_rules(path: Path = DEFAULT_RULES_FILE) -> ClassifierRules:
    if not path.exists():
        raise FileNotFoundError(f"Classifier rules file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return rules_from_dict(data)


def rules_from_dict(data: dict[str, Any]) -> ClassifierRules:
    return ClassifierRules(
        important_header_terms=_tuple(data.get("important_header_terms", [])),
        junk_terms=_tuple(data.get("junk_terms", [])),
        promo_senders=_tuple(data.get("promo_senders", [])),
        always_forward_senders=_tuple(data.get("always_forward_senders", [])),
        always_forward_subjects=_tuple(data.get("always_forward_subjects", [])),
        always_junk_senders=_tuple(data.get("always_junk_senders", [])),
        always_junk_subjects=_tuple(data.get("always_junk_subjects", [])),
        ignore_patterns=tuple(
            SenderSubjectRule(
                sender=str(rule.get("sender", "")).lower(),
                subject=str(rule.get("subject", "")).lower(),
                reason=str(rule.get("reason", "")),
            )
            for rule in data.get("ignore_patterns", [])
        ),
        sender_content_rules=tuple(
            SenderContentRule(
                sender=str(rule.get("sender", "")).lower(),
                forward_subject_terms=_tuple(rule.get("forward_subject_terms", [])),
                junk_terms=_tuple(rule.get("junk_terms", [])),
                forward_reason=str(rule.get("forward_reason", "important cue")),
                junk_reason=str(rule.get("junk_reason", "review preference")),
                uncertain_reason=str(
                    rule.get("uncertain_reason", "uncertain; forwarding to avoid false negative")
                ),
            )
            for rule in data.get("sender_content_rules", [])
        ),
        bulk_headers=_tuple(data.get("bulk_headers", [])),
    )


def _tuple(values: list[Any]) -> tuple[str, ...]:
    return tuple(str(value).lower() for value in values)


def _header(message: EmailMessage, name: str) -> str:
    return str(message.get(name, ""))


def _matches(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


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
