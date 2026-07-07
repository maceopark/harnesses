from __future__ import annotations

from dataclasses import dataclass
from typing import Any

OPEN = "open"
DONE = "done"


@dataclass
class Task:
    id: int
    title: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "status": self.status}



@dataclass
class Store:
    next_id: int
    tasks: list[Task]

    def to_dict(self) -> dict[str, Any]:
        return {"next_id": self.next_id, "tasks": [task.to_dict() for task in self.tasks]}

