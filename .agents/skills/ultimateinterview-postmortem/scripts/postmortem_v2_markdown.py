from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

CAL_SKELETON_TRANSLATION: Final[Mapping[int, str]] = MappingProxyType({
    **dict.fromkeys(
        (
            0x237A, 0xFF41, 0x1D41A, 0x1D44E, 0x1D482, 0x1D4B6, 0x1D4EA, 0x1D51E,
            0x1D552, 0x1D586, 0x1D5BA, 0x1D5EE, 0x1D622, 0x1D656, 0x1D68A, 0x0251,
            0x03B1, 0x1D6C2, 0x1D6FC, 0x1D736, 0x1D770, 0x1D7AA, 0x0430, 0xFF21,
            0x1CCD6, 0x1D400, 0x1D434, 0x1D468, 0x1D49C, 0x1D4D0, 0x1D504, 0x1D538,
            0x1D56C, 0x1D5A0, 0x1D5D4, 0x1D608, 0x1D63C, 0x1D670, 0x0391, 0x1D6A8,
            0x1D6E2, 0x1D71C, 0x1D756, 0x1D790, 0x0410, 0x13AA, 0x15C5, 0xA4EE,
            0x16F40, 0x102A0,
        ),
        "a",
    ),
    **dict.fromkeys(
        (
            0xFF43, 0x217D, 0x1D41C, 0x1D450, 0x1D484, 0x1D4B8, 0x1D4EC, 0x1D520,
            0x1D554, 0x1D588, 0x1D5BC, 0x1D5F0, 0x1D624, 0x1D658, 0x1D68C, 0x1D04,
            0x03F2, 0x2CA5, 0x0441, 0x1004, 0x105A, 0xABAF, 0x1043D, 0x1F74C,
            0x118E9, 0x118F2, 0xFF23, 0x216D, 0x2102, 0x212D, 0x1CCD8, 0x1D402,
            0x1D436, 0x1D46A, 0x1D49E, 0x1D4D2, 0x1D56E, 0x1D5A2, 0x1D5D6, 0x1D60A,
            0x1D63E, 0x1D672, 0x03F9, 0x2CA4, 0x0421, 0x13DF, 0xA4DA, 0x102A2,
            0x10302, 0x10415, 0x1051C,
        ),
        "c",
    ),
    **dict.fromkeys(
        (
            0x05C0, 0x2223, 0x23FD, 0xFFE8, 0x0661, 0x06F1,
            0x10320, 0x1E8C7, 0x1CCF1, 0x1D7CF, 0x1D7D9, 0x1D7E3, 0x1D7ED, 0x1D7F7,
            0x1FBF1, 0xFF29, 0x2160, 0x2110, 0x2111, 0x1CCDE, 0x1D408,
            0x1D43C, 0x1D470, 0x1D4D8, 0x1D540, 0x1D574, 0x1D5A8, 0x1D5DC, 0x1D610,
            0x1D644, 0x1D678, 0x0196, 0xFF4C, 0x217C, 0x2113, 0x1D425, 0x1D459,
            0x1D48D, 0x1D4C1, 0x1D4F5, 0x1D529, 0x1D55D, 0x1D591, 0x1D5C5, 0x1D5F9,
            0x1D62D, 0x1D661, 0x1D695, 0x01C0, 0x0399, 0x1D6B0, 0x1D6EA, 0x1D724,
            0x1D75E, 0x1D798, 0x2C92, 0x0406, 0x04CF, 0x04C0, 0x05D5, 0x05DF, 0x0627,
            0x1EE00, 0x1EE80, 0xFE8E, 0xFE8D, 0x07CA, 0x2D4F, 0x16C1, 0xA4F2,
            0x16F28, 0x1028A, 0x10309, 0x11DDA, 0x11DE1, 0x16EAA, 0x1D22A, 0x216C,
            0x2112, 0x1CCE1, 0x1D40B, 0x1D43F, 0x1D473, 0x1D4DB, 0x1D50F, 0x1D543,
            0x1D577, 0x1D5AB, 0x1D5DF, 0x1D613, 0x1D647, 0x1D67B, 0x2CD0, 0x13DE,
            0x14AA, 0xA4E1, 0x16F16, 0x118A3, 0x118B2, 0x1041B, 0x10526,
        ),
        "l",
    ),
})
BIDI_CONTROLS: Final[frozenset[str]] = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _inline_link_labels(value: str) -> str:
    text: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "[":
            text.append(value[index])
            index += 1
            continue
        label_end = value.find("]", index + 1)
        if label_end < 0 or label_end + 1 == len(value) or value[label_end + 1] != "(":
            text.append(value[index])
            index += 1
            continue
        depth = 0
        destination_end = label_end + 1
        while destination_end < len(value):
            character = value[destination_end]
            if character == "\\" and destination_end + 1 < len(value):
                destination_end += 2
                continue
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    text.append(value[index + 1 : label_end])
                    index = destination_end + 1
                    break
            destination_end += 1
        else:
            text.append(value[index])
            index += 1
    return "".join(text)


def _visible_markdown(value: str) -> str:
    without_html = re.sub(r"<!--.*?-->|<[^>]*>", "", html.unescape(value), flags=re.DOTALL)
    return re.sub(r"\[([^]]+)\]\[[^]]*\]", r"\1", _inline_link_labels(without_html))


def _normalized(value: str, translation: Mapping[int, str] | None = None) -> str:
    visible = _visible_markdown(value)
    source = visible.translate(translation) if translation else visible
    normalized = unicodedata.normalize("NFKD", source)
    normalized = normalized.translate(str.maketrans("", "", "*_`~\\"))
    return "".join(character for character in normalized if unicodedata.category(character) not in {"Cf", "Mn"})


def identifier_skeleton(value: str) -> str:
    return _normalized(value, CAL_SKELETON_TRANSLATION)


def has_bidi_synthetic_candidate(value: str) -> bool:
    return any(
        any(character in BIDI_CONTROLS for character in token)
        and any(character in "-‐‑‒–—−" for character in token)
        and re.fullmatch(r"cal\d{3}", re.sub(r"[^a-z0-9]", "", identifier_skeleton(token).lower())) is not None
        for token in _visible_markdown(value).split()
    )
