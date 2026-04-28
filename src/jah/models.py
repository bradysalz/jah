from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


VALID_STATUSES = {"todo", "draft", "in-progress", "completed", "scrapped"}
DONE_STATUSES = {"completed", "scrapped"}
KANBAN_COLUMNS = ("DRAFT", "TODO", "WIP", "DONE")
STATUS_TO_COLUMN = {
    "todo": "TODO",
    "draft": "DRAFT",
    "in-progress": "WIP",
    "completed": "DONE",
    "scrapped": "DONE",
}
PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


@dataclass(frozen=True)
class Ticket:
    id: str
    title: str
    status: str
    parent: Optional[str]
    path: Path
    body: str = ""
    type: Optional[str] = None
    priority: Optional[str] = None
    tags: Tuple[str, ...] = ()
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def is_done(self) -> bool:
        return self.status in DONE_STATUSES

    def matches(self, query: str) -> bool:
        needle = query.strip().lower()
        if not needle:
            return True
        haystacks = [self.title, self.body, " ".join(self.tags)]
        return any(needle in haystack.lower() for haystack in haystacks)


@dataclass(frozen=True)
class TicketGraph:
    tickets: Dict[str, Ticket]
    children: Dict[str, Tuple[str, ...]]
    roots: Tuple[str, ...]

    def ticket(self, ticket_id: str) -> Ticket:
        return self.tickets[ticket_id]

    def is_leaf(self, ticket_id: str) -> bool:
        return len(self.children.get(ticket_id, ())) == 0

    def ancestors(self, ticket_id: str) -> Tuple[str, ...]:
        ids: List[str] = []
        current = self.tickets[ticket_id].parent
        while current and current in self.tickets:
            ids.append(current)
            current = self.tickets[current].parent
        return tuple(ids)

    def descendants(self, ticket_id: str) -> Tuple[str, ...]:
        found: List[str] = []
        stack = list(reversed(self.children.get(ticket_id, ())))
        while stack:
            current = stack.pop()
            found.append(current)
            stack.extend(reversed(self.children.get(current, ())))
        return tuple(found)


def build_graph(tickets: Iterable[Ticket]) -> TicketGraph:
    by_id = {ticket.id: ticket for ticket in tickets}
    cyclic_ids = _find_cyclic_ids(by_id)
    if cyclic_ids:
        by_id = {ticket_id: ticket for ticket_id, ticket in by_id.items() if ticket_id not in cyclic_ids}

    children: Dict[str, List[str]] = {ticket_id: [] for ticket_id in by_id}
    roots: List[str] = []

    for ticket in sorted(by_id.values(), key=lambda item: (item.created_at or "", item.id)):
        if ticket.parent and ticket.parent in by_id:
            children[ticket.parent].append(ticket.id)
        else:
            roots.append(ticket.id)

    immutable_children = {ticket_id: tuple(ids) for ticket_id, ids in children.items()}
    return TicketGraph(tickets=by_id, children=immutable_children, roots=tuple(roots))


def _find_cyclic_ids(tickets: Dict[str, Ticket]) -> Set[str]:
    visiting: Set[str] = set()
    visited: Set[str] = set()
    cyclic: Set[str] = set()

    def visit(ticket_id: str, path: List[str]) -> None:
        if ticket_id in visited:
            return
        if ticket_id in visiting:
            cycle_start = path.index(ticket_id)
            cyclic.update(path[cycle_start:])
            return

        visiting.add(ticket_id)
        path.append(ticket_id)
        parent = tickets[ticket_id].parent
        if parent and parent in tickets:
            visit(parent, path)
        path.pop()
        visiting.remove(ticket_id)
        visited.add(ticket_id)

    for ticket_id in tickets:
        visit(ticket_id, [])
    return cyclic


def tree_rows(
    graph: TicketGraph,
    query: str = "",
    hide_done: bool = False,
    expanded_ids: Optional[Set[str]] = None,
    visible_statuses: Optional[Set[str]] = None,
) -> List[Tuple[str, int, bool, bool]]:
    candidate_ids = _tree_candidate_ids(graph, query)
    candidate_ids = _apply_tree_status_filter(graph, candidate_ids, visible_statuses)
    if hide_done:
        candidate_ids = _apply_tree_done_filter(graph, candidate_ids)

    rows: List[Tuple[str, int, bool, bool]] = []
    expanded = expanded_ids if expanded_ids is not None else set(graph.tickets)

    def walk(ticket_id: str, depth: int) -> None:
        if ticket_id not in candidate_ids:
            return
        children = [child for child in graph.children.get(ticket_id, ()) if child in candidate_ids]
        is_expanded = ticket_id in expanded
        rows.append((ticket_id, depth, bool(children), is_expanded))
        if is_expanded:
            for child_id in children:
                walk(child_id, depth + 1)

    for root_id in graph.roots:
        walk(root_id, 0)
    return rows


def kanban_columns(
    graph: TicketGraph,
    query: str = "",
    hide_done: bool = False,
    visible_statuses: Optional[Set[str]] = None,
) -> Dict[str, List[str]]:
    columns = {column: [] for column in KANBAN_COLUMNS}
    allowed_statuses = visible_statuses if visible_statuses is not None else VALID_STATUSES
    for ticket_id, ticket in graph.tickets.items():
        if not graph.is_leaf(ticket_id):
            continue
        if ticket.status not in allowed_statuses:
            continue
        if hide_done and ticket.is_done:
            continue
        if not ticket.matches(query):
            continue
        columns[STATUS_TO_COLUMN[ticket.status]].append(ticket_id)

    for column_ids in columns.values():
        column_ids.sort(key=lambda ticket_id: _kanban_sort_key(graph.tickets[ticket_id]))
    return columns


def all_expanded_ids(graph: TicketGraph) -> Set[str]:
    return {ticket_id for ticket_id, children in graph.children.items() if children}


def _tree_candidate_ids(graph: TicketGraph, query: str) -> Set[str]:
    if not query.strip():
        return set(graph.tickets)

    candidate_ids: Set[str] = set()
    for ticket_id, ticket in graph.tickets.items():
        if ticket.matches(query):
            candidate_ids.add(ticket_id)
            candidate_ids.update(graph.ancestors(ticket_id))
    return candidate_ids


def _apply_tree_done_filter(graph: TicketGraph, candidate_ids: Set[str]) -> Set[str]:
    visible: Set[str] = set()

    def has_active_visible_descendant(ticket_id: str) -> bool:
        for descendant_id in graph.descendants(ticket_id):
            if descendant_id in candidate_ids and not graph.ticket(descendant_id).is_done:
                return True
        return False

    for ticket_id in candidate_ids:
        ticket = graph.ticket(ticket_id)
        if not ticket.is_done or has_active_visible_descendant(ticket_id):
            visible.add(ticket_id)
    return visible


def _apply_tree_status_filter(
    graph: TicketGraph,
    candidate_ids: Set[str],
    visible_statuses: Optional[Set[str]],
) -> Set[str]:
    allowed_statuses = visible_statuses if visible_statuses is not None else VALID_STATUSES
    if allowed_statuses == VALID_STATUSES:
        return candidate_ids

    visible: Set[str] = set()
    for ticket_id in candidate_ids:
        if graph.ticket(ticket_id).status in allowed_statuses:
            visible.add(ticket_id)
            visible.update(ancestor_id for ancestor_id in graph.ancestors(ticket_id) if ancestor_id in candidate_ids)
    return visible


def _kanban_sort_key(ticket: Ticket) -> Tuple[int, str, str]:
    priority_rank = PRIORITY_RANK.get(ticket.priority or "normal", PRIORITY_RANK["normal"])
    return priority_rank, ticket.created_at or "", ticket.id
