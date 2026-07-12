"""Today-view derivation and rendering.

All semantics derive at render time from stored dates (REQ-011); "today" is the system
local date, overridable via TODO_TODAY=YYYY-MM-DD (test seam only).
"""

from __future__ import annotations

import datetime as dt
import os

OVERDUE_MARK = "[기한 지남!]"
DONE_MARK = "✓"
_PRI_RANK = {"high": 0, "mid": 1, "low": 2}


def today() -> dt.date:
    override = os.environ.get("TODO_TODAY")
    if override:
        return dt.date.fromisoformat(override)
    return dt.date.today()


def open_items_in_view(data: dict, day: dt.date) -> list[dict]:
    """Open items visible today, in display order (positions = 1-based indexes here)."""
    visible = [
        item
        for item in data["items"]
        if item["done_on"] is None
        and (item["due"] is None or dt.date.fromisoformat(item["due"]) <= day)
    ]
    visible.sort(key=lambda item: (_PRI_RANK[item["pri"]], item["seq"]))
    return visible


def done_today_items(data: dict, day: dt.date) -> list[dict]:
    return [item for item in data["items"] if item["done_on"] == day.isoformat()]


def render_view(data: dict, day: dt.date) -> str:
    lines: list[str] = []
    open_items = open_items_in_view(data, day)
    for pos, item in enumerate(open_items, start=1):
        parts = [f"{pos}. {item['title']}"]
        if item["pri"] != "mid":
            parts.append(f"[{item['pri']}]")
        if item["due"] is not None:
            if dt.date.fromisoformat(item["due"]) < day:
                parts.append(OVERDUE_MARK)
            else:
                parts.append(f"(due {item['due']})")
        lines.append("  " + " ".join(parts))
    for item in done_today_items(data, day):
        lines.append(f"  {DONE_MARK} {item['title']} (오늘 완료)")
    if not lines:
        lines.append("  (오늘 할일 없음)")
    return "\n".join(lines)
