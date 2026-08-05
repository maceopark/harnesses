"""Lexical gold-implementation leakage checks for public artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping


_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b")
_PATH = re.compile(r"(?<![\w.-])(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
_ADDED_LINE = re.compile(r"^\+(?!\+\+\+)(.*)$")
_SAFE_WORDS = frozenset(
    {"true", "false", "none", "self", "return", "class", "async", "await", "raise"}
)


@dataclass(frozen=True, slots=True)
class LeakageFinding:
    kind: str
    sentinel: str
    location: str


def patch_only_sentinels(
    patch_text: str,
    *,
    public_issue_text: str = "",
    base_repository_text: str = "",
    minimum_fragment_length: int = 24,
) -> dict[str, frozenset[str]]:
    """Extract identifiers, paths, and fragments introduced only by a gold patch."""
    provenance = f"{public_issue_text}\n{base_repository_text}"
    added = [match.group(1).strip() for line in patch_text.splitlines() if (match := _ADDED_LINE.match(line))]
    identifiers = {
        token
        for line in added
        for token in _IDENTIFIER.findall(line)
        if token.lower() not in _SAFE_WORDS and token not in provenance
    }
    paths = {
        path
        for line in added
        for path in _PATH.findall(line)
        if path not in provenance
    }
    fragments = {
        line
        for line in added
        if len(line.encode("utf-8")) >= minimum_fragment_length
        and not line.startswith(("#", "//"))
        and line not in provenance
    }
    return {
        "identifier": frozenset(identifiers),
        "path": frozenset(paths),
        "code_fragment": frozenset(fragments),
    }


def lexical_leakage_findings(
    public_text: str,
    sentinels: Mapping[str, Iterable[str]],
    *,
    location: str = "$",
) -> list[LeakageFinding]:
    findings: list[LeakageFinding] = []
    for kind in sorted(sentinels):
        for sentinel in sorted(set(sentinels[kind]), key=lambda value: (-len(value), value)):
            if not sentinel:
                continue
            if kind == "identifier":
                found = re.search(rf"(?<![A-Za-z0-9_]){re.escape(sentinel)}(?![A-Za-z0-9_])", public_text)
            else:
                found = sentinel in public_text
            if found:
                findings.append(LeakageFinding(kind, sentinel, location))
    return findings


def audit_public_payload(
    payload: object, sentinels: Mapping[str, Iterable[str]], *, location: str = "$"
) -> list[LeakageFinding]:
    """Recursively audit both keys and values; any finding must fail the caller closed."""
    findings: list[LeakageFinding] = []
    if isinstance(payload, str):
        return lexical_leakage_findings(payload, sentinels, location=location)
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_location = f"{location}.{key}"
            findings.extend(lexical_leakage_findings(str(key), sentinels, location=key_location))
            findings.extend(audit_public_payload(value, sentinels, location=key_location))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            findings.extend(audit_public_payload(value, sentinels, location=f"{location}[{index}]"))
    return findings

