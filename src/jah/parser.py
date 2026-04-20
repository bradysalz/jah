from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import yaml

from jah.models import Ticket, VALID_STATUSES, build_graph


def load_graph(directory: Path):
    return build_graph(load_tickets(directory))


def load_tickets(directory: Path) -> List[Ticket]:
    tickets: List[Ticket] = []
    for path in sorted(directory.glob("*.md")):
        ticket = parse_ticket(path)
        if ticket is not None:
            tickets.append(ticket)
    return tickets


def parse_ticket(path: Path) -> Optional[Ticket]:
    text = path.read_text(encoding="utf-8")
    metadata, body, frontmatter = split_frontmatter(text)
    if not metadata:
        return None

    status = str(metadata.get("status", "")).strip()
    if status not in VALID_STATUSES:
        return None

    ticket_id = str(metadata.get("id") or _frontmatter_comment_id(frontmatter) or _filename_id(path)).strip()
    title = str(metadata.get("title") or ticket_id).strip()
    parent = metadata.get("parent")
    tags = metadata.get("tags") or []

    return Ticket(
        id=ticket_id,
        title=title,
        status=status,
        parent=str(parent).strip() if parent else None,
        path=path,
        body=body.strip(),
        type=_optional_str(metadata.get("type")),
        priority=_optional_str(metadata.get("priority")),
        tags=tuple(str(tag) for tag in tags),
        created_at=_optional_str(metadata.get("created_at")),
        updated_at=_optional_str(metadata.get("updated_at")),
    )


def split_frontmatter(text: str) -> Tuple[dict, str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, ""

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            parsed = yaml.safe_load(frontmatter) or {}
            if not isinstance(parsed, dict):
                return {}, body, frontmatter
            return parsed, body, frontmatter
    return {}, text, ""


def _frontmatter_comment_id(frontmatter: str) -> Optional[str]:
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or None
    return None


def _filename_id(path: Path) -> str:
    return path.stem.split("--", 1)[0]


def _optional_str(value) -> Optional[str]:
    if value is None:
        return None
    return str(value)
