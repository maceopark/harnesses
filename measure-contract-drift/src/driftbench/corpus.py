"""Public development corpus validation and private simulator vocabulary types.

Controller-visible corpus artifacts contain only development prompts and their starter
trees. Evaluation annotations, simulator lexicons, and every holdout record belong to
trusted private fixtures and are deliberately not loadable from this module's public
loader.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Literal
from unicodedata import category, normalize

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


DEV_CASE_COUNT = 12
CASE_ID_RE = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
OPAQUE_TOKEN_RE = re.compile(r"[a-z0-9]{8,32}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_DEV_DOMAINS = frozenset(
    {
        "bookmarks",
        "access-grant",
        "appointment-reschedule",
        "config-merge",
        "contacts-csv",
        "expense",
        "feature-flags",
        "inventory-transfer",
        "order-cancel",
        "playlist-reorder",
        "reminder",
        "todo",
    }
)


class CorpusValidationError(ValueError):
    """Raised when a public corpus artifact is malformed or self-inconsistent."""


class StrictModel(BaseModel):
    """A closed, immutable JSON-compatible artifact model."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, populate_by_name=True)


def _utf8_nfc_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field_name} must be UTF-8 encodable") from error
    if normalize("NFC", value) != value:
        raise ValueError(f"{field_name} must be NFC normalized")
    if not value or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be nonblank and trimmed")
    return value


def _identifier(value: str, field_name: str, pattern: re.Pattern[str]) -> str:
    value = _utf8_nfc_text(value, field_name)
    if not pattern.fullmatch(value):
        raise ValueError(f"{field_name} has an invalid identifier shape")
    return value


def _sha256(value: str, field_name: str) -> str:
    value = _utf8_nfc_text(value, field_name)
    if not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise CorpusValidationError("value is not canonical JSON") from error


def _tokens(value: str) -> tuple[str, ...]:
    """Normalize text exactly as the private simulator's lexical matching path does."""

    value = _utf8_nfc_text(value, "rule term").casefold()
    parts: list[str] = []
    current: list[str] = []
    for character in value:
        if character.isspace() or category(character).startswith("P"):
            if current:
                parts.append("".join(current))
                current.clear()
        else:
            current.append(character)
    if current:
        parts.append("".join(current))
    if not parts:
        raise ValueError("rule term must contain at least one non-punctuation token")
    return tuple(parts)


class SimulatorRule(StrictModel):
    """Private-service vocabulary model; it is never accepted from public corpus input."""

    rule_id: str
    tier: Literal["choice", "intent", "lexical"]
    terms: tuple[str, ...] = Field(min_length=1, max_length=8)
    response_class: Literal["clarification", "boundary", "acknowledgement"]

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        return _identifier(value, "rule_id", CASE_ID_RE)

    @field_validator("terms")
    @classmethod
    def validate_terms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        terms = tuple(_utf8_nfc_text(term, "simulator term") for term in value)
        for term in terms:
            _tokens(term)
        return terms

    @property
    def token_multiset(self) -> Counter[str]:
        return Counter(token for term in self.terms for token in _tokens(term))

    @property
    def specificity(self) -> int:
        return sum(self.token_multiset.values())


class SimulatorLexicon(StrictModel):
    """Private-service lexicon type retained for the simulator boundary."""

    schema_: Literal["SimulatorLexicon.v1"] = Field(
        default="SimulatorLexicon.v1", alias="schema", serialization_alias="schema"
    )
    case_id: str
    rules: tuple[SimulatorRule, ...] = Field(min_length=3, max_length=24)

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        return _identifier(value, "case_id", CASE_ID_RE)

    @model_validator(mode="after")
    def validate_rules(self) -> "SimulatorLexicon":
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("simulator rule_id values must be unique")
        tiers = {rule.tier for rule in self.rules}
        if tiers != {"choice", "intent", "lexical"}:
            raise ValueError("simulator lexicon requires choice, intent, and lexical rules")
        signatures = [(rule.tier, tuple(sorted(rule.token_multiset.items()))) for rule in self.rules]
        if len(set(signatures)) != len(signatures):
            raise ValueError("simulator rules cannot share a tier and token multiset")
        return self


class PublicCaseRecord(StrictModel):
    """A controller-visible development prompt and binding to its starter tree."""

    schema_: Literal["PublicCaseRecord.v1"] = Field(
        default="PublicCaseRecord.v1", alias="schema", serialization_alias="schema"
    )
    case_id: str
    opaque_token: str
    partition: Literal["dev"] = "dev"
    prompt: str
    starter_tree: str
    starter_digest: str

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        return _identifier(value, "case_id", CASE_ID_RE)

    @field_validator("opaque_token")
    @classmethod
    def validate_opaque_token(cls, value: str) -> str:
        return _identifier(value, "opaque_token", OPAQUE_TOKEN_RE)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return _utf8_nfc_text(value, "prompt")

    @field_validator("starter_tree")
    @classmethod
    def validate_starter_tree(cls, value: str) -> str:
        value = _utf8_nfc_text(value, "starter_tree")
        path = PurePosixPath(value)
        if path.is_absolute() or path.parts[:1] != ("starters",) or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("starter_tree must be a relative path below starters")
        if len(path.parts) != 2 or not CASE_ID_RE.fullmatch(path.parts[1]):
            raise ValueError("starter_tree must name one case directory")
        return value

    @field_validator("starter_digest")
    @classmethod
    def validate_starter_digest(cls, value: str) -> str:
        return _sha256(value, "starter_digest")

    @model_validator(mode="after")
    def validate_starter_binding(self) -> "PublicCaseRecord":
        if self.starter_tree != f"starters/{self.case_id}":
            raise ValueError("starter_tree must bind the record's case_id")
        return self


class PublicCorpusDocument(StrictModel):
    schema_: Literal["DriftBenchPublicCorpus.v3"] = Field(
        default="DriftBenchPublicCorpus.v3", alias="schema", serialization_alias="schema"
    )
    release_id: str
    cases: tuple[PublicCaseRecord, ...]

    @field_validator("release_id")
    @classmethod
    def validate_release_id(cls, value: str) -> str:
        return _identifier(value, "release_id", CASE_ID_RE)

    @model_validator(mode="after")
    def validate_cases(self) -> "PublicCorpusDocument":
        case_ids = [case.case_id for case in self.cases]
        opaque_tokens = [case.opaque_token for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case_id values must be unique")
        if len(set(opaque_tokens)) != len(opaque_tokens):
            raise ValueError("opaque_token values must be unique")
        if case_ids != sorted(case_ids):
            raise ValueError("cases must be sorted by case_id for deterministic loading")
        return self


class PublicCorpusManifest(StrictModel):
    schema_: Literal["DriftBenchPublicManifest.v3"] = Field(
        default="DriftBenchPublicManifest.v3", alias="schema", serialization_alias="schema"
    )
    release_id: str
    cases_file: Literal["cases.json"] = "cases.json"
    dev_tokens: tuple[str, ...]
    case_digests: dict[str, str]
    public_scope: Literal["dev-prompts-and-starters-only"] = "dev-prompts-and-starters-only"
    assurance: Literal["none"] = "none"

    @field_validator("release_id")
    @classmethod
    def validate_release_id(cls, value: str) -> str:
        return _identifier(value, "release_id", CASE_ID_RE)

    @field_validator("dev_tokens")
    @classmethod
    def validate_dev_tokens(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        tokens = tuple(_identifier(token, "dev token", OPAQUE_TOKEN_RE) for token in value)
        if tokens != tuple(sorted(tokens)):
            raise ValueError("dev_tokens must be sorted")
        if len(set(tokens)) != len(tokens):
            raise ValueError("dev_tokens must be unique")
        return tokens

    @field_validator("case_digests")
    @classmethod
    def validate_case_digests(cls, value: Mapping[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("case_digests must not be empty")
        digests = {
            _identifier(token, "case digest token", OPAQUE_TOKEN_RE): _sha256(digest, "case digest")
            for token, digest in value.items()
        }
        if list(digests) != sorted(digests):
            raise ValueError("case_digests must be keyed in sorted token order")
        return digests


# Backwards-compatible public names. They intentionally refer only to public records.
CaseRecord = PublicCaseRecord
CorpusDocument = PublicCorpusDocument
CorpusManifest = PublicCorpusManifest


def case_digest(record: PublicCaseRecord) -> str:
    """Hash the canonical public development record."""

    return sha256(_canonical_json(record.model_dump(mode="json", by_alias=True)).encode("utf-8")).hexdigest()


def corpus_digest(records: Sequence[PublicCaseRecord]) -> str:
    """Hash public case digests in canonical case-id order."""

    ordered = sorted(records, key=lambda record: record.case_id)
    payload = [{"case_id": record.case_id, "digest": case_digest(record)} for record in ordered]
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def starter_tree_digest(tree_root: str | Path) -> str:
    """Hash the exact regular-file content of one non-empty starter tree."""

    root = Path(tree_root)
    if root.is_symlink() or not root.is_dir():
        raise CorpusValidationError(f"starter tree is absent or unsafe: {root}")
    entries: list[dict[str, str]] = []

    def walk(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as error:
            raise CorpusValidationError(f"cannot read starter tree: {root}") from error
        for entry in children:
            if entry.is_symlink():
                raise CorpusValidationError(f"starter tree contains a symlink: {entry}")
            if entry.is_dir():
                walk(entry)
                continue
            if not entry.is_file():
                raise CorpusValidationError(f"starter tree contains an unsafe entry: {entry}")
            try:
                contents = entry.read_bytes()
            except OSError as error:
                raise CorpusValidationError(f"cannot read starter tree: {root}") from error
            entries.append(
                {
                    "path": entry.relative_to(root).as_posix(),
                    "sha256": sha256(contents).hexdigest(),
                }
            )

    walk(root)
    if not entries:
        raise CorpusValidationError(f"starter tree must contain a regular file: {root}")
    return sha256(_canonical_json(entries).encode("utf-8")).hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CorpusValidationError(f"cannot read corpus artifact: {path}") from error
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CorpusValidationError(f"invalid JSON in corpus artifact: {path}") from error
    if not isinstance(payload, dict):
        raise CorpusValidationError(f"corpus artifact must be a JSON object: {path}")
    return payload


def load_cases(path: str | Path) -> list[PublicCaseRecord]:
    """Load only controller-visible development prompt records."""

    source = Path(path)
    try:
        document = PublicCorpusDocument.model_validate(_load_json_object(source))
    except ValidationError as error:
        raise CorpusValidationError(f"invalid public case corpus: {source}") from error
    return list(document.cases)


def load_manifest(path: str | Path) -> PublicCorpusManifest:
    """Load the public development digest binding without any private partition data."""

    source = Path(path)
    try:
        return PublicCorpusManifest.model_validate(_load_json_object(source))
    except ValidationError as error:
        raise CorpusValidationError(f"invalid public corpus manifest: {source}") from error


def _starter_tree_for_case(public_root: Path, case: PublicCaseRecord) -> Path:
    tree = public_root
    for component in PurePosixPath(case.starter_tree).parts:
        tree = tree / component
        if tree.is_symlink():
            raise CorpusValidationError(f"starter tree path contains a symlink: {tree}")
    return tree
def _validated_starter_tree(public_root: Path, case: PublicCaseRecord) -> Path:
    tree = _starter_tree_for_case(public_root, case)
    if starter_tree_digest(tree) != case.starter_digest:
        raise CorpusValidationError("starter digest does not match the public starter tree")
    return tree


def materialize_starter_tree(
    public_root: str | Path,
    case: PublicCaseRecord,
    destination: str | Path,
) -> Path:
    """Copy one digest-validated starter into a new, otherwise empty destination."""

    source = _validated_starter_tree(Path(public_root), case)
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise CorpusValidationError(f"starter destination already exists or is unsafe: {target}")
    parent = target.parent
    if parent.is_symlink() or not parent.is_dir():
        raise CorpusValidationError(f"starter destination parent is absent or unsafe: {parent}")
    try:
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=parent))
        shutil.copytree(source, staging, dirs_exist_ok=True)
        if starter_tree_digest(staging) != case.starter_digest:
            raise CorpusValidationError("materialized starter digest does not match the case binding")
        staging.replace(target)
    except CorpusValidationError:
        if "staging" in locals() and staging.exists():
            shutil.rmtree(staging)
        raise
    except OSError as error:
        if "staging" in locals() and staging.exists():
            shutil.rmtree(staging)
        raise CorpusValidationError(f"cannot materialize starter tree: {source}") from error
    return target


def validate_corpus(
    cases_path: str | Path,
    manifest_path: str | Path | None = None,
    partition: Literal["dev"] | None = None,
) -> list[PublicCaseRecord]:
    """Fail closed unless the public development corpus and starter trees bind exactly."""

    if partition not in (None, "dev"):
        raise CorpusValidationError("public corpus only supports the development partition")
    source = Path(cases_path)
    cases = load_cases(source)
    if len(cases) != DEV_CASE_COUNT:
        raise CorpusValidationError(f"public corpus must contain exactly {DEV_CASE_COUNT} development cases")
    if {case.case_id for case in cases} != REQUIRED_DEV_DOMAINS:
        raise CorpusValidationError("public corpus does not contain the fixed development domains")
    manifest_source = Path(manifest_path) if manifest_path is not None else source.with_name("manifest.json")
    manifest = load_manifest(manifest_source)
    document = PublicCorpusDocument.model_validate(_load_json_object(source))
    if document.release_id != manifest.release_id:
        raise CorpusValidationError("manifest release_id does not bind the public case corpus")
    tokens = {case.opaque_token for case in cases}
    if len(manifest.dev_tokens) != DEV_CASE_COUNT:
        raise CorpusValidationError(
            f"manifest must bind exactly {DEV_CASE_COUNT} development tokens"
        )
    if tokens != set(manifest.dev_tokens) or tokens != set(manifest.case_digests):
        raise CorpusValidationError("manifest tokens must bind every and only public case")
    for case in cases:
        if manifest.case_digests[case.opaque_token] != case_digest(case):
            raise CorpusValidationError("case digest does not match manifest binding")
        _validated_starter_tree(source.parent, case)
    return cases


__all__ = [
    "CASE_ID_RE",
    "DEV_CASE_COUNT",
    "CaseRecord",
    "CorpusDocument",
    "CorpusManifest",
    "CorpusValidationError",
    "PublicCaseRecord",
    "PublicCorpusDocument",
    "PublicCorpusManifest",
    "SimulatorLexicon",
    "SimulatorRule",
    "case_digest",
    "corpus_digest",
    "load_cases",
    "load_manifest",
    "starter_tree_digest",
    "materialize_starter_tree",
    "validate_corpus",
]
