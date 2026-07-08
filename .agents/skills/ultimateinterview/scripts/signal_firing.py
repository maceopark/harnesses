#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
#      uv run scripts/signal_firing.py "<request text>"
#      uv run scripts/signal_firing.py "<request text>" --touched-code "foo.py bar.py"
#      uv run scripts/signal_firing.py "<request text>" --format json
# ──────────────────
#
# SIGNAL-FIRING CHECK (closed-loop guide, "One rule before editing the skill
# itself" — half 2a).
#
# A true before/after discovery RATE needs a full human-in-the-loop cycle
# (re-interview -> new spec -> re-implement -> re-postmortem). This is the cheap,
# STATIC half: given a request's text (plus optionally the touched-code terms),
# deterministically report which lenses the CURRENT Orientation triggers +
# lessons signals would fire on. It cannot prove the escape gets caught, but a
# trigger that STOPS firing on a request whose escape it targets is a measurable
# regression — exactly what this catches.
#
# The triggers are PARSED from the source of truth at runtime, not hard-coded:
#   - references/orientation.md  §Lens triggers  (the parenthetical word-lists,
#     the "such as" quality words, the hyphenated tokens, and the comma-listed
#     trigger phrases)
#   - lessons.md                 the ACTIVE fire-tracking rows (Retired skipped)
# So deleting a trigger word from orientation.md removes it from this oracle, and
# a canonical case that depended on it fails in test_signal_firing.py. That is
# the regression signal for the 2026-07 "experimental" rules (temporal-word and
# reject-category triggers especially).
#
# Precision policy: only HIGH-PRECISION signals are matched — parsed word-lists,
# hyphenated tokens, and multi-word trigger phrases (as substrings). Generic
# single words from prose triggers are NOT auto-matched (too noisy); a small,
# clearly-labelled curated synonym set (source "heuristic") covers common short
# phrasings. Every fire reports its matched token AND its source, so a human can
# audit whether a fire is rule-derived or heuristic.

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SELF_DIR = Path(__file__).resolve().parent
DEFAULT_ORIENTATION = SELF_DIR.parent / "references" / "orientation.md"
DEFAULT_LESSONS = SELF_DIR.parent / "lessons.md"

LENSES = ["viewpoint", "domain/state", "goal/obstacle", "misuse", "quality", "controlled-language"]

# Curated synonyms (source "heuristic"): short phrasings a real request uses that
# the orientation prose implies but does not spell out. Kept tight on purpose;
# test_signal_firing.py::test_heuristic_anchors_still_in_orientation guards that
# each maps to trigger language still present in orientation.md.
HEURISTIC_SYNONYMS: dict[str, list[str]] = {
    "misuse": ["delete", "deletion", "remove", "destroy", "wipe", "overwrite",
               "password", "credential", "token", "injection"],
    "domain/state": ["state machine", "status transition"],
}

_STOP = {
    "the", "a", "an", "or", "and", "of", "in", "on", "to", "its", "with", "that",
    "any", "such", "as", "is", "then", "goal", "request", "named", "without",
    "deciding", "attributes", "significant", "surface", "accepting", "values",
    "impact", "potential", "actions", "access", "changes", "data",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_orientation(path: Path) -> dict[str, dict]:
    """Return {lens: {"words": set, "phrases": set, "raw": str}} from §Lens triggers."""
    triggers: dict[str, dict] = {}
    if not path.is_file():
        return triggers
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^Lens triggers:\s*$(.*?)^For each untriggered", text, re.S | re.M)
    block = m.group(1) if m else text
    for line in block.splitlines():
        bm = re.match(r"\s*-\s*`([^`]+)`:\s*(.*)", line)
        if not bm:
            continue
        lens, body = bm.group(1).strip(), bm.group(2).strip()
        words: set[str] = set()
        phrases: set[str] = set()

        # 1. parenthetical word-lists (the temporal words, the reject categories).
        #    Keep a parenthetical only if, before any " - " note, it is a comma
        #    list of short (1-2 word) alpha tokens.
        for paren in re.findall(r"\(([^)]*)\)", body):
            head = paren.split(" - ")[0]
            items = [i.strip() for i in head.split(",")]
            good = [i for i in items if i and re.fullmatch(r"[a-z][a-z -]*", i) and len(i.split()) <= 2]
            if len(good) >= 2:  # a genuine word-list, not a prose note
                words.update(w for w in good if len(w) >= 3)

        # strip all parentheticals before tokenizing the rest
        rest = re.sub(r"\([^)]*\)", "", body)

        # 2. "such as X, Y, Z" -> single quality words
        sm = re.search(r"such as (.+)", rest)
        such = sm.group(1) if sm else ""
        for frag in re.split(r",| or ", such):
            frag = frag.strip().rstrip(".")
            if frag and re.fullmatch(r"[a-z]{3,}", frag):
                words.add(frag)
        if sm:
            rest = rest[: sm.start()]

        # 3. comma / "or" separated trigger phrases -> phrase substrings + hyphenated tokens
        for frag in re.split(r",| or ", rest):
            frag = _clean(re.sub(r"such as.*", "", frag))
            frag = frag.strip(" .")
            if not frag:
                continue
            for hy in re.findall(r"[a-z]+-[a-z]+", frag):  # free-text, user-supplied, long-lived
                words.add(hy)
            toks = [t for t in frag.split() if t not in _STOP]
            if len(toks) >= 2:
                phrases.add(" ".join(toks))
            elif len(toks) == 1 and len(toks[0]) >= 4:
                words.add(toks[0])

        triggers[lens] = {"words": words, "phrases": phrases, "raw": body}
    return triggers


def parse_lessons(paths: list[Path]) -> list[dict]:
    """Active (non-Retired) lessons rows -> [{lens, tokens, signal, source}]."""
    rows: list[dict] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        active = re.split(r"^##\s*Retired", text, maxsplit=1, flags=re.M)[0]
        for line in active.splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            signal, lens = cells[0], cells[1]
            if signal.lower() in ("signal", "") or set(signal) <= {"-", " ", ":"}:
                continue  # header / separator row
            if lens not in LENSES:
                continue
            low = _clean(signal)
            toks: list[str] = []
            for w in re.findall(r"[a-z][a-z-]{4,}", low):
                if w not in _STOP and w not in toks:
                    toks.append(w)
            rows.append({
                "lens": lens,
                "tokens": toks[:8],
                "signal": signal[:70],
                "source": f"lessons:{path.name}",
            })
    return rows


def _word_hit(word: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None


def fire(request: str, triggers: dict[str, dict], lessons: list[dict],
         touched: str = "") -> dict[str, list[dict]]:
    """Return {lens: [{token, kind, source}]} for every lens that fires."""
    text = _clean(request + " " + touched)
    result: dict[str, list[dict]] = {}

    for lens, data in triggers.items():
        hits: list[dict] = []
        for w in sorted(data["words"]):
            if _word_hit(w, text):
                hits.append({"token": w, "kind": "word", "source": "orientation"})
        for p in sorted(data["phrases"]):
            if p in text:
                hits.append({"token": p, "kind": "phrase", "source": "orientation"})
        for syn in HEURISTIC_SYNONYMS.get(lens, []):
            hit = syn in text if " " in syn else _word_hit(syn, text)
            if hit:
                hits.append({"token": syn, "kind": "synonym", "source": "heuristic"})
        if hits:
            result.setdefault(lens, []).extend(hits)

    # lessons rows fire only when >=2 distinct tokens appear (avoids one common
    # word like "store" firing a whole store-lesson row on its own).
    for row in lessons:
        matched = [t for t in row["tokens"] if _word_hit(t, text)]
        if len(matched) >= 2:
            result.setdefault(row["lens"], []).append(
                {"token": "+".join(matched), "kind": "lesson", "source": row["source"]}
            )
    return result


def load(orientation: Path, lessons_paths: list[Path]):
    return parse_orientation(orientation), parse_lessons(lessons_paths)


def main() -> int:
    ap = argparse.ArgumentParser(description="Report which lenses the current triggers fire on a request.")
    ap.add_argument("request", help="the request / goal text to test")
    ap.add_argument("--touched-code", default="", help="terms from touched files/code (searched too)")
    ap.add_argument("--orientation", type=Path, default=DEFAULT_ORIENTATION)
    ap.add_argument("--lessons", type=Path, action="append", default=None,
                    help="lessons store(s); repeatable. Defaults to the skill-local lessons.md")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = ap.parse_args()

    lessons_paths = args.lessons or [DEFAULT_LESSONS]
    triggers, lessons = load(args.orientation, lessons_paths)
    fired = fire(args.request, triggers, lessons, args.touched_code)

    if args.format == "json":
        print(json.dumps({"fired": fired, "lenses_fired": sorted(fired)}, indent=2))
        return 0

    print("## Signal-firing check\n")
    print(f"request: {args.request!r}")
    if args.touched_code:
        print(f"touched-code: {args.touched_code!r}")
    print(f"\ntriggers parsed from: {args.orientation.name} + {[p.name for p in lessons_paths]}\n")
    if not fired:
        print("No lens fires. (core path only — no triggered lens.)")
        return 0
    for lens in LENSES:
        if lens in fired:
            toks = ", ".join(f"{h['token']} [{h['source']}]" for h in fired[lens])
            print(f"- `{lens}` FIRES — {toks}")
    quiet = [l for l in LENSES if l not in fired]
    if quiet:
        print(f"\nnot fired: {', '.join(quiet)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
